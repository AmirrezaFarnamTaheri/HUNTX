package main

// HuntX Telegram Configs Collector (Go)
// Fetches proxy configurations from public Telegram channels since the last run.

import (
	"bufio"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"
)

const (
	channelsFile   = "telegram_channels.json"
	lastUpdateFile = "last_update.txt"
	outputFile     = "collected_configs.txt"
	irOutputFile   = "ir_configs.txt"
	irB64File      = "irb64.txt"
	userAgent      = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
	requestDelay   = 100 * time.Millisecond
	maxConcurrency = 10
)

var blockedProbeNetworks = mustNetworks(
	"0.0.0.0/8",
	"10.0.0.0/8",
	"100.64.0.0/10",
	"127.0.0.0/8",
	"169.254.0.0/16",
	"172.16.0.0/12",
	"192.0.0.0/24",
	"192.0.2.0/24",
	"192.168.0.0/16",
	"198.18.0.0/15",
	"198.51.100.0/24",
	"203.0.113.0/24",
	"224.0.0.0/4",
	"240.0.0.0/4",
	"::/128",
	"::1/128",
	"fc00::/7",
	"fe80::/10",
	"ff00::/8",
	"2001:db8::/32",
)

func mustNetworks(cidrs ...string) []*net.IPNet {
	networks := make([]*net.IPNet, 0, len(cidrs))
	for _, cidr := range cidrs {
		_, network, err := net.ParseCIDR(cidr)
		if err != nil {
			panic(err)
		}
		networks = append(networks, network)
	}
	return networks
}

func isPublicProbeIP(ip net.IP) bool {
	if ip == nil || !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() ||
		ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsMulticast() ||
		ip.IsUnspecified() {
		return false
	}
	for _, network := range blockedProbeNetworks {
		if network.Contains(ip) {
			return false
		}
	}
	return true
}

type ChannelResult struct {
	Channel  string
	Messages []string
	Error    error
}

type ConnectionResult struct {
	ConfigStr string
	Latency   time.Duration
}

func decodeVMessPayload(encoded string) ([]byte, error) {
	encodings := []*base64.Encoding{
		base64.StdEncoding,
		base64.RawStdEncoding,
		base64.URLEncoding,
		base64.RawURLEncoding,
	}
	var lastErr error
	for _, encoding := range encodings {
		decoded, err := encoding.DecodeString(encoded)
		if err == nil {
			return decoded, nil
		}
		lastErr = err
	}
	return nil, lastErr
}

func parseConfigPort(value interface{}) (int, error) {
	var port int
	switch raw := value.(type) {
	case float64:
		port = int(raw)
	case string:
		parsed, err := strconv.Atoi(raw)
		if err != nil {
			return 0, err
		}
		port = parsed
	case json.Number:
		parsed, err := strconv.Atoi(raw.String())
		if err != nil {
			return 0, err
		}
		port = parsed
	default:
		return 0, fmt.Errorf("unsupported port type %T", value)
	}
	if port < 1 || port > 65535 {
		return 0, fmt.Errorf("port outside valid range: %d", port)
	}
	return port, nil
}

// extractAddressPort extracts IP/domain and port from a proxy config URL.
func extractAddressPort(configStr string) (string, int, error) {
	if strings.HasPrefix(configStr, "vmess://") {
		encodedPart := configStr[8:]
		decoded, err := decodeVMessPayload(encodedPart)
		if err != nil {
			return "", 0, fmt.Errorf("failed to decode VMess config: %v", err)
		}

		var vmessData map[string]interface{}
		decoder := json.NewDecoder(strings.NewReader(string(decoded)))
		decoder.UseNumber()
		if err := decoder.Decode(&vmessData); err != nil {
			return "", 0, fmt.Errorf("failed to parse VMess JSON: %v", err)
		}

		address, ok := vmessData["add"].(string)
		if !ok || strings.TrimSpace(address) == "" {
			return "", 0, fmt.Errorf("VMess config missing address")
		}

		port, err := parseConfigPort(vmessData["port"])
		if err != nil {
			return "", 0, fmt.Errorf("VMess config has invalid port: %v", err)
		}
		return address, port, nil
	}

	parsedURL, err := url.Parse(configStr)
	if err != nil {
		return "", 0, fmt.Errorf("failed to parse config URL: %v", err)
	}

	address := parsedURL.Hostname()
	if address == "" {
		return "", 0, fmt.Errorf("config missing address")
	}

	port := parsedURL.Port()
	if port == "" {
		switch parsedURL.Scheme {
		case "ss":
			port = "8388"
		case "trojan", "vless":
			port = "443"
		default:
			port = "443"
		}
	}

	portInt, err := strconv.Atoi(port)
	if err != nil || portInt < 1 || portInt > 65535 {
		return "", 0, fmt.Errorf("invalid port: %q", port)
	}
	return address, portInt, nil
}

func resolveDomainToIPs(domain string) ([]string, error) {
	if parsed := net.ParseIP(domain); parsed != nil {
		if !isPublicProbeIP(parsed) {
			return nil, fmt.Errorf("refusing non-public endpoint %s", domain)
		}
		return []string{parsed.String()}, nil
	}

	ips, err := net.LookupIP(domain)
	if err != nil {
		return nil, err
	}

	seen := make(map[string]struct{})
	ipStrings := make([]string, 0, len(ips))
	for _, ip := range ips {
		if !isPublicProbeIP(ip) {
			continue
		}
		value := ip.String()
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		ipStrings = append(ipStrings, value)
	}
	if len(ipStrings) == 0 {
		return nil, fmt.Errorf("domain %s resolved only to non-public addresses", domain)
	}
	return ipStrings, nil
}

// checkPort tests if a port is open on a validated public IP.
func checkPort(ip string, port int, timeout time.Duration) bool {
	parsedIP := net.ParseIP(ip)
	if !isPublicProbeIP(parsedIP) || port < 1 || port > 65535 || timeout <= 0 {
		return false
	}
	address := net.JoinHostPort(parsedIP.String(), strconv.Itoa(port))

	conn, err := net.DialTimeout("tcp", address, timeout)
	if err != nil {
		return false
	}
	_ = conn.Close()
	return true
}

// testConnection tests if a proxy config is working by checking public-endpoint connectivity.
func testConnection(configStr string) (*ConnectionResult, error) {
	address, port, err := extractAddressPort(configStr)
	if err != nil {
		return nil, fmt.Errorf("failed to extract address/port: %v", err)
	}

	ips, err := resolveDomainToIPs(address)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve safe public endpoint: %v", err)
	}

	for _, ip := range ips {
		if checkPort(ip, port, 1*time.Second) {
			return &ConnectionResult{
				ConfigStr: configStr,
				Latency:   100 * time.Millisecond,
			}, nil
		}
	}

	return nil, fmt.Errorf("no working public IP/port combination found")
}

// testConfigsFromSlice tests multiple configs concurrently and returns only working ones.
func testConfigsFromSlice(configs []string, concurrency int) []string {
	if concurrency < 1 {
		concurrency = 1
	}
	semaphore := make(chan struct{}, concurrency)
	var wg sync.WaitGroup
	resultsChan := make(chan *ConnectionResult, len(configs))

	for _, config := range configs {
		wg.Add(1)
		go func(cfg string) {
			defer wg.Done()

			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			if result, err := testConnection(cfg); err == nil {
				resultsChan <- result
			}
		}(config)
	}

	go func() {
		wg.Wait()
		close(resultsChan)
	}()

	var workingConfigs []string
	for result := range resultsChan {
		workingConfigs = append(workingConfigs, result.ConfigStr)
	}

	fmt.Printf("✅ Connection testing complete. Found %d working configurations out of %d\n",
		len(workingConfigs), len(configs))

	return workingConfigs
}

type ConfigCollection struct {
	Shadowsocks []string `json:"shadowsocks"`
	Trojan      []string `json:"trojan"`
	Vmess       []string `json:"vmess"`
	Vless       []string `json:"vless"`
	Reality     []string `json:"reality"`
	Tuic        []string `json:"tuic"`
	Hysteria    []string `json:"hysteria"`
	Juicity     []string `json:"juicity"`
}

var patterns = map[string]*regexp.Regexp{
	"telegramUser": regexp.MustCompile(`@(\w{4,})`),
	"url":          regexp.MustCompile(`https?://[^\s<>#]+`),
	"shadowsocks":  regexp.MustCompile(`ss://[^\s<>#]+`),
	"trojan":       regexp.MustCompile(`trojan://[^\s<>#]+`),
	"vmess":        regexp.MustCompile(`vmess://[^\s<>#]+`),
	"vless":        regexp.MustCompile(`vless://[^\s<>#]+`),
	"reality":      regexp.MustCompile(`vless://[^\s<>#]*security=reality[^\s<>#]*`),
	"tuic":         regexp.MustCompile(`tuic://[^\s<>#]+`),
	"hysteria":     regexp.MustCompile(`hysteria://[^\s<>#]+`),
	"hysteria2":    regexp.MustCompile(`hy2://[^\s<>#]+`),
	"juicity":      regexp.MustCompile(`juicity://[^\s<>#]+`),
}

func loadTelegramChannels() ([]string, error) {
	file, err := os.Open(channelsFile)
	if err != nil {
		return nil, fmt.Errorf("error opening channels file: %v", err)
	}
	defer file.Close()

	var channels []string
	decoder := json.NewDecoder(file)
	if err := decoder.Decode(&channels); err != nil {
		return nil, fmt.Errorf("error decoding channels JSON: %v", err)
	}

	return channels, nil
}

func loadLastUpdate() (time.Time, error) {
	file, err := os.Open(lastUpdateFile)
	if err != nil {
		if os.IsNotExist(err) {
			return time.Now().AddDate(0, 0, -3), nil
		}
		return time.Time{}, err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	if scanner.Scan() {
		timestamp := strings.TrimSpace(scanner.Text())
		if parsed, err := time.Parse(time.RFC3339, timestamp); err == nil {
			return parsed, nil
		}
	}

	return time.Now().AddDate(0, 0, -3), nil
}

func saveLastUpdate(timestamp time.Time) error {
	file, err := os.Create(lastUpdateFile)
	if err != nil {
		return err
	}
	defer file.Close()

	_, err = fmt.Fprintln(file, timestamp.Format(time.RFC3339))
	return err
}

func fetchChannelMessages(channelUser string) ([]string, error) {
	url := fmt.Sprintf("https://t.me/s/%s", channelUser)

	client := &http.Client{
		Timeout: 10 * time.Second,
	}

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("User-Agent", userAgent)

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, err
	}

	var messages []string

	doc.Find(".tgme_widget_message").Each(func(i int, s *goquery.Selection) {
		textElement := s.Find(".tgme_widget_message_text")
		if textElement.Length() == 0 {
			return
		}

		html, err := textElement.Html()
		if err != nil {
			return
		}

		text := cleanHTMLText(html)
		if text != "" {
			messages = append(messages, text)
		}
	})

	return messages, nil
}

func cleanHTMLText(html string) string {
	html = regexp.MustCompile(`<code>([^<>]+)</code>`).ReplaceAllString(html, "$1")
	html = regexp.MustCompile(`<a[^<>]+>([^<>]+)</a>`).ReplaceAllString(html, "$1")
	html = regexp.MustCompile(`<[^>]+>`).ReplaceAllString(html, "")
	html = regexp.MustCompile(`\s+`).ReplaceAllString(html, " ")

	return strings.TrimSpace(html)
}

func extractConfigs(text string) ConfigCollection {
	collection := ConfigCollection{}

	protocolMap := map[string]*[]string{
		"shadowsocks": &collection.Shadowsocks,
		"trojan":      &collection.Trojan,
		"vmess":       &collection.Vmess,
		"vless":       &collection.Vless,
		"reality":     &collection.Reality,
		"tuic":        &collection.Tuic,
		"hysteria":    &collection.Hysteria,
		"juicity":     &collection.Juicity,
	}

	for key, slice := range protocolMap {
		if matches := patterns[key].FindAllString(text, -1); matches != nil {
			for _, match := range matches {
				cleanMatch := regexp.MustCompile(`#[^#]+$`).ReplaceAllString(match, "")
				if !strings.Contains(cleanMatch, "…") {
					*slice = append(*slice, cleanMatch)
				}
			}
		}
	}

	if matches := patterns["hysteria2"].FindAllString(text, -1); matches != nil {
		for _, match := range matches {
			cleanMatch := regexp.MustCompile(`#[^#]+$`).ReplaceAllString(match, "")
			if !strings.Contains(cleanMatch, "…") {
				collection.Hysteria = append(collection.Hysteria, cleanMatch)
			}
		}
	}

	return collection
}

func processChannelsConcurrently(channels []string) ([]ChannelResult, int) {
	results := make([]ChannelResult, 0, len(channels))
	resultsChan := make(chan ChannelResult, len(channels))
	semaphore := make(chan struct{}, maxConcurrency)
	var wg sync.WaitGroup

	for i, channel := range channels {
		wg.Add(1)
		go func(index int, ch string) {
			defer wg.Done()

			semaphore <- struct{}{}
			defer func() { <-semaphore }()

			fmt.Printf("🔍 Checking channel %d/%d: %s\n", index+1, len(channels), ch)

			messages, err := fetchChannelMessages(ch)
			result := ChannelResult{
				Channel:  ch,
				Messages: messages,
				Error:    err,
			}

			if err != nil {
				fmt.Printf("❌ Error fetching %s: %v\n", ch, err)
			} else {
				fmt.Printf("📨 Found %d messages in %s\n", len(messages), ch)
			}

			resultsChan <- result
			time.Sleep(requestDelay)
		}(i, channel)
	}

	go func() {
		wg.Wait()
		close(resultsChan)
	}()

	totalMessages := 0
	for result := range resultsChan {
		results = append(results, result)
		if result.Error == nil {
			totalMessages += len(result.Messages)
		}
	}

	return results, totalMessages
}

func removeDuplicates(slice []string) []string {
	keys := make(map[string]bool)
	var result []string

	for _, item := range slice {
		if !keys[item] {
			keys[item] = true
			result = append(result, item)
		}
	}

	return result
}

func filterIranianConfigs(configs []string) []string {
	var irConfigs []string

	irDomains := []string{
		".ir",
		"samanehha.co",
		"webramz.co",
		"felafel.org",
		"bazibazestan.ir",
		"arman19.space",
		"freexnum01tamiz",
		"series-a2",
		"admin.c1",
		"freakconfig",
		"soft98",
		"speedtest.net",
	}

	for _, config := range configs {
		isIranian := false

		for _, domain := range irDomains {
			if strings.Contains(config, domain) {
				isIranian = true
				break
			}
		}

		if strings.Contains(config, "🔹با") || strings.Contains(config, "با") {
			isIranian = true
		}

		if strings.Contains(config, " - IR") || strings.Contains(config, " - ir") {
			isIranian = true
		}

		if isIranian {
			irConfigs = append(irConfigs, config)
		}
	}

	return irConfigs
}

func main() {
	fmt.Println("🚀 Starting HuntX Collector...")

	channels, err := loadTelegramChannels()
	if err != nil {
		log.Fatalf("Error loading channels: %v", err)
	}

	lastUpdate, err := loadLastUpdate()
	if err != nil {
		log.Fatalf("Error loading last update: %v", err)
	}

	currentTime := time.Now()

	fmt.Printf("📅 Last update: %s\n", lastUpdate.Format(time.RFC3339))
	fmt.Printf("📅 Current time: %s\n", currentTime.Format(time.RFC3339))
	fmt.Printf("📋 Channels to check: %d\n", len(channels))
	fmt.Printf("⚡ Processing with max %d concurrent requests\n", maxConcurrency)

	allConfigs := ConfigCollection{}

	fmt.Println("🔍 Starting concurrent channel processing...")
	results, totalNewMessages := processChannelsConcurrently(channels)

	fmt.Printf("\n📨 Total messages processed: %d\n", totalNewMessages)

	for _, result := range results {
		if result.Error != nil {
			continue
		}

		for _, message := range result.Messages {
			configs := extractConfigs(message)
			allConfigs.Shadowsocks = append(allConfigs.Shadowsocks, configs.Shadowsocks...)
			allConfigs.Trojan = append(allConfigs.Trojan, configs.Trojan...)
			allConfigs.Vmess = append(allConfigs.Vmess, configs.Vmess...)
			allConfigs.Vless = append(allConfigs.Vless, configs.Vless...)
			allConfigs.Reality = append(allConfigs.Reality, configs.Reality...)
			allConfigs.Tuic = append(allConfigs.Tuic, configs.Tuic...)
			allConfigs.Hysteria = append(allConfigs.Hysteria, configs.Hysteria...)
			allConfigs.Juicity = append(allConfigs.Juicity, configs.Juicity...)
		}
	}

	fmt.Printf("\n📊 Total messages processed: %d\n", totalNewMessages)

	fmt.Println("🔧 Removing duplicates...")
	allConfigs.Shadowsocks = removeDuplicates(allConfigs.Shadowsocks)
	allConfigs.Trojan = removeDuplicates(allConfigs.Trojan)
	allConfigs.Vmess = removeDuplicates(allConfigs.Vmess)
	allConfigs.Vless = removeDuplicates(allConfigs.Vless)
	allConfigs.Reality = removeDuplicates(allConfigs.Reality)
	allConfigs.Tuic = removeDuplicates(allConfigs.Tuic)
	allConfigs.Hysteria = removeDuplicates(allConfigs.Hysteria)
	allConfigs.Juicity = removeDuplicates(allConfigs.Juicity)

	fmt.Printf("🔧 Shadowsocks: %d unique configs\n", len(allConfigs.Shadowsocks))
	fmt.Printf("🔧 Trojan: %d unique configs\n", len(allConfigs.Trojan))
	fmt.Printf("🔧 Vmess: %d unique configs\n", len(allConfigs.Vmess))
	fmt.Printf("🔧 Vless: %d unique configs\n", len(allConfigs.Vless))
	fmt.Printf("🔧 Reality: %d unique configs\n", len(allConfigs.Reality))
	fmt.Printf("🔧 Tuic: %d unique configs\n", len(allConfigs.Tuic))
	fmt.Printf("🔧 Hysteria: %d unique configs\n", len(allConfigs.Hysteria))
	fmt.Printf("🔧 Juicity: %d unique configs\n", len(allConfigs.Juicity))

	allCombined := append(allConfigs.Shadowsocks,
		append(allConfigs.Trojan,
			append(allConfigs.Vmess,
				append(allConfigs.Vless,
					append(allConfigs.Reality,
						append(allConfigs.Tuic,
							append(allConfigs.Hysteria, allConfigs.Juicity...)...)...)...)...)...)...)

	fmt.Printf("📦 Total unique configs: %d\n", len(allCombined))

	if err := saveConfigsToFile(allCombined); err != nil {
		log.Fatalf("Error saving configs: %v", err)
	}

	fmt.Println("🇮🇷 Filtering Iranian configs...")
	irConfigs := removeDuplicates(filterIranianConfigs(allCombined))
	fmt.Printf("🇮🇷 Found %d unique Iranian configs\n", len(irConfigs))

	fmt.Println("🔍 Testing Iranian configs for connectivity...")
	workingIrConfigs := testConfigsFromSlice(irConfigs, maxConcurrency)
	fmt.Printf("✅ Found %d working Iranian configurations out of %d\n",
		len(workingIrConfigs), len(irConfigs))

	if err := saveConfigsToFileWithName(workingIrConfigs, irOutputFile); err != nil {
		log.Fatalf("Error saving working IR configs: %v", err)
	}

	if err := saveConfigsToFileBase64(workingIrConfigs, irB64File); err != nil {
		log.Fatalf("Error saving base64 IR configs: %v", err)
	}
	fmt.Printf("📦 Created base64 encoded file: %s\n", irB64File)

	if err := saveLastUpdate(currentTime); err != nil {
		log.Fatalf("Error saving last update: %v", err)
	}

	fmt.Println("✅ Collection complete!")
}

func saveConfigsToFile(configs []string) error {
	return saveConfigsToFileWithName(configs, outputFile)
}

func saveConfigsToFileWithName(configs []string, filename string) error {
	file, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer file.Close()

	writer := bufio.NewWriter(file)
	for _, config := range configs {
		if _, err := fmt.Fprintln(writer, config); err != nil {
			return err
		}
	}

	return writer.Flush()
}

func saveConfigsToFileBase64(configs []string, filename string) error {
	file, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer file.Close()

	writer := bufio.NewWriter(file)
	for _, config := range configs {
		encoded := base64.StdEncoding.EncodeToString([]byte(config))
		if _, err := fmt.Fprintln(writer, encoded); err != nil {
			return err
		}
	}

	return writer.Flush()
}
