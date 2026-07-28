package outputverify

import (
	"archive/zip"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/AmirrezaFarnamTaheri/HUNTX/internal/releasemanifest"
)

type Summary struct {
	Files      int            `json:"files"`
	TotalSize  int64          `json:"total_size"`
	Protocols  map[string]int `json:"protocols"`
	Formats    map[string]int `json:"formats"`
	VmessCount int            `json:"vmess_count"`
}

var proxySchemes = []string{"vmess://", "vless://", "trojan://", "ss://", "ssr://", "hysteria2://", "hy2://", "tuic://", "wireguard://", "socks://", "socks5://", "juicity://", "anytls://"}

func Verify(dataDir string) (Summary, error) {
	outputDir := filepath.Join(dataDir, "outputs")
	info, err := os.Stat(outputDir)
	if err != nil || !info.IsDir() {
		return Summary{}, errors.New("output directory does not exist")
	}
	stage, err := os.MkdirTemp(dataDir, ".dist-stage-")
	if err != nil {
		return Summary{}, err
	}
	defer os.RemoveAll(stage)
	summary := Summary{Protocols: map[string]int{}, Formats: map[string]int{}}
	paths := []string{}
	if err := filepath.WalkDir(outputDir, func(name string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil { return walkErr }
		if name == outputDir { return nil }
		if entry.Type()&os.ModeSymlink != 0 { return fmt.Errorf("symlink output forbidden: %s", name) }
		if entry.IsDir() { return nil }
		paths = append(paths, name)
		return nil
	}); err != nil { return Summary{}, err }
	sort.Strings(paths)
	if len(paths) == 0 { return Summary{}, errors.New("no output artifacts found") }
	for _, name := range paths {
		payload, err := os.ReadFile(name)
		if err != nil { return Summary{}, err }
		if len(payload) == 0 { return Summary{}, fmt.Errorf("empty output artifact: %s", name) }
		if err := validate(name, payload, &summary); err != nil { return Summary{}, err }
		rel, err := filepath.Rel(outputDir, name)
		if err != nil { return Summary{}, err }
		dest := filepath.Join(stage, rel)
		if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil { return Summary{}, err }
		if err := os.WriteFile(dest, payload, 0o600); err != nil { return Summary{}, err }
		summary.Files++
		summary.TotalSize += int64(len(payload))
	}
	manifestPath := filepath.Join(stage, "manifest.json")
	candidates, err := releasemanifest.Discover(stage, manifestPath)
	if err != nil { return Summary{}, err }
	manifest, err := releasemanifest.Build(stage, candidates)
	if err != nil { return Summary{}, err }
	if err := releasemanifest.WriteAtomic(manifestPath, manifest); err != nil { return Summary{}, err }
	if err := releasemanifest.Verify(stage, manifest); err != nil { return Summary{}, err }
	if err := promoteDirectory(stage, filepath.Join(dataDir, "dist")); err != nil { return Summary{}, err }
	return summary, nil
}

func validate(name string, payload []byte, summary *Summary) error {
	lower := strings.ToLower(name)
	summary.Formats[filepath.Ext(lower)]++
	if strings.HasSuffix(lower, ".json") {
		var value any
		if err := json.Unmarshal(payload, &value); err != nil { return err }
	}
	if strings.HasSuffix(lower, ".zip") {
		reader, err := zip.OpenReader(name)
		if err != nil { return err }
		defer reader.Close()
	}
	text := strings.TrimSpace(string(payload))
	if decoded, err := decodeBase64(text); err == nil && strings.Contains(string(decoded), "://") { text = string(decoded) }
	for _, line := range strings.Split(text, "\n") {
		for _, scheme := range proxySchemes {
			if strings.HasPrefix(strings.TrimSpace(line), scheme) {
				protocol := strings.TrimSuffix(scheme, "://")
				summary.Protocols[protocol]++
				if protocol == "vmess" { summary.VmessCount++ }
			}
		}
	}
	return nil
}

func decodeBase64(value string) ([]byte, error) {
	value = strings.TrimSpace(value)
	return base64.StdEncoding.DecodeString(value + strings.Repeat("=", (4-len(value)%4)%4))
}

func promoteDirectory(stage, target string) error {
	backup := target + ".backup"
	_ = os.RemoveAll(backup)
	hadOld := false
	if _, err := os.Stat(target); err == nil {
		if err := os.Rename(target, backup); err != nil { return err }
		hadOld = true
	} else if !os.IsNotExist(err) { return err }
	if err := os.Rename(stage, target); err != nil {
		if hadOld { _ = os.Rename(backup, target) }
		return err
	}
	if hadOld { return os.RemoveAll(backup) }
	return nil
}
