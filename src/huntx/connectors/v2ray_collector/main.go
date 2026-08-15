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

type ChannelResult struct {
	Channel  string
	Messages []string
	Error    error
}

type ConnectionResult struct {
	ConfigStr string
	Latency   time.Duration
}

// extractAddressPort extracts IP/domain and port from a proxy config URL
func extractAddressPort(configStr string) (string, int, error) {
	if strings.HasPrefix(configStr, "vmess://") {
		encodedPart := configStr[8:]
		decoded, err := base64.StdEncoding.DecodeString(encodedPart)
		if err != nil {
			return "", 0, fmt.Errorf("failed to decode VMess config: %v", err)
		}

		var vmessData map[string]interface{}
		if err := json.Unmarshal(decoded, &vmessData); err != nil {
			return "", 0, fmt.Errorf("failed to parse VMess JSON: %v", err)
		}

		address, ok := vmessData["add"].(string)
		if !ok {
			return "", 0, fmt.Errorf("VMess config missing address")
		}

		portFloat, ok := vmessData["port"].(float64)
		if !ok {
			return "", 0, fmt.Errorf("VMess config missing port")
		}

		return address, int(portFloat), nil
	} else {
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
			case "trojan":
				port = "443"
			case "vless":
				port = "443"
			default:
				port = "443"
			}
		}

		portInt, err := strconv.Atoi(port)
		if err != nil {
			return "", 0, fmt.Errorf("invalid port: %v", err)
		}

		return address, portInt, nil
	}
}

func resolveDomainToIPs(domain string) ([]string, error) {
	if net.ParseIP(domain) != nil {
		return []string{domain}, nil
	}

	ips, err := net.LookupIP(domain)
	if err != nil {
		return []string{domain}, nil
	}

	var ipStrings []string
	for _, ip := range ips {
		ipStrings = append(ipStrings, ip.String())
	}

	return ipStrings, nil
}

// checkPort tests if a port is open on the given IP
func checkPort(ip string, port int, timeout time.Duration) bool {
	address := fmt.Sprintf("%s:%d", ip, port)

	conn, err := net.DialTimeout("tcp", address, timeout)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

// testConnection tests if a proxy config is working by checking port connectivity
func testConnection(configStr string) (*ConnectionResult, error) {
	address, port, err := extractAddressPort(configStr)
	if err != nil {
		return nil, fmt.Errorf("failed to extract address/port: %v", err)
	}

	ips, err := resolveDomainToIPs(address)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve domain: %v", err)
	}

	for _, ip := range ips {
		if checkPort(ip, port, 1*time.Second) {
			return &ConnectionResult{
				ConfigStr: configStr,
				Latency:   100 * time.Millisecond,
			}, nil
		}
	}

	return nil, fmt.Errorf("no working IP/port combination found")
}

// testConfigsFromSlice tests multiple configs concurrently and returns only working ones
func testConfigsFromSlice(configs []string, maxConcurrency int) []string {
	semaphore := make(chan struct{}, maxConcurrency)
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

	// Close results channel when all workers are done
	go func() {
		wg.Wait()
		close(resultsChan)
	}()

	// Collect working configs
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

	// Extract protocol configs
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

	// Handle hysteria2 separately
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

	// Start workers
	for i, channel := range channels {
		wg.Add(1)
		go func(index int, ch string) {
			defer wg.Done()

			// Acquire semaphore
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

			// Small delay between requests to be respectful
			time.Sleep(requestDelay)
		}(i, channel)
	}

	// Close results channel when all workers are done
	go func() {
		wg.Wait()
		close(resultsChan)
	}()

	// Collect results
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

	// Iranian domain patterns
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

		// Check for Iranian domains
		for _, domain := range irDomains {
			if strings.Contains(config, domain) {
				isIranian = true
				break
			}
		}

		// Check for Persian characters in config (common in Iranian configs)
		if strings.Contains(config, "🔹با") || strings.Contains(config, "با") {
			isIranian = true
		}

		// Check for IR country code in remarks (format: "Name - IR-Other")
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

	// Load channels
	channels, err := loadTelegramChannels()
	if err != nil {
		log.Fatalf("Error loading channels: %v", err)
	}

	// Load last update
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

	// Process channels concurrently
	fmt.Println("� Starting concurrent channel processing...")
	results, totalNewMessages := processChannelsConcurrently(channels)

	fmt.Printf("\n� Total messages processed: %d\n", totalNewMessages)

	// Extract configs from all messages
	for _, result := range results {
		if result.Error != nil {
			continue
		}

		for _, message := range result.Messages {
			configs := extractConfigs(message)

			// Add to collections
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

	// Remove duplicates
	fmt.Println("🔧 Removing duplicates...")
	allConfigs.Shadowsocks = removeDuplicates(allConfigs.Shadowsocks)
	allConfigs.Trojan = removeDuplicates(allConfigs.Trojan)
	allConfigs.Vmess = removeDuplicates(allConfigs.Vmess)
	allConfigs.Vless = removeDuplicates(allConfigs.Vless)
	allConfigs.Reality = removeDuplicates(allConfigs.Reality)
	allConfigs.Tuic = removeDuplicates(allConfigs.Tuic)
	allConfigs.Hysteria = removeDuplicates(allConfigs.Hysteria)
	allConfigs.Juicity = removeDuplicates(allConfigs.Juicity)

	// Print stats
	fmt.Printf("🔧 Shadowsocks: %d unique configs\n", len(allConfigs.Shadowsocks))
	fmt.Printf("🔧 Trojan: %d unique configs\n", len(allConfigs.Trojan))
	fmt.Printf("🔧 Vmess: %d unique configs\n", len(allConfigs.Vmess))
	fmt.Printf("🔧 Vless: %d unique configs\n", len(allConfigs.Vless))
	fmt.Printf("🔧 Reality: %d unique configs\n", len(allConfigs.Reality))
	fmt.Printf("🔧 Tuic: %d unique configs\n", len(allConfigs.Tuic))
	fmt.Printf("🔧 Hysteria: %d unique configs\n", len(allConfigs.Hysteria))
	fmt.Printf("🔧 Juicity: %d unique configs\n", len(allConfigs.Juicity))

	// Combine all configs
	allCombined := append(allConfigs.Shadowsocks,
		append(allConfigs.Trojan,
			append(allConfigs.Vmess,
				append(allConfigs.Vless,
					append(allConfigs.Reality,
						append(allConfigs.Tuic,
							append(allConfigs.Hysteria, allConfigs.Juicity...)...)...)...)...)...)...)

	fmt.Printf("📦 Total unique configs: %d\n", len(allCombined))

	// Save to file
	if err := saveConfigsToFile(allCombined); err != nil {
		log.Fatalf("Error saving configs: %v", err)
	}

	// Filter and save Iranian configs
	fmt.Println("🇮🇷 Filtering Iranian configs...")
	irConfigs := filterIranianConfigs(allCombined)
	irConfigs = removeDuplicates(irConfigs)

	fmt.Printf("🇮🇷 Found %d unique Iranian configs\n", len(irConfigs))

	// Test Iranian configs for connectivity (only save working ones)
	fmt.Println("🔍 Testing Iranian configs for connectivity...")
	workingIrConfigs := testConfigsFromSlice(irConfigs, maxConcurrency)

	fmt.Printf("✅ Found %d working Iranian configurations out of %d\n",
		len(workingIrConfigs), len(irConfigs))

	if err := saveConfigsToFileWithName(workingIrConfigs, irOutputFile); err != nil {
		log.Fatalf("Error saving working IR configs: %v", err)
	}

	// Create base64 encoded version
	if err := saveConfigsToFileBase64(workingIrConfigs, irB64File); err != nil {
		log.Fatalf("Error saving base64 IR configs: %v", err)
	}
	fmt.Printf("📦 Created base64 encoded file: %s\n", irB64File)

	// Update last update timestamp
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
		// Base64 encode each config
		encoded := base64.StdEncoding.EncodeToString([]byte(config))
		if _, err := fmt.Fprintln(writer, encoded); err != nil {
			return err
		}
	}

	return writer.Flush()
}
