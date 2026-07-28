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

var proxySchemes = []string{
	"vmess://",
	"vless://",
	"trojan://",
	"ss://",
	"ssr://",
	"hysteria2://",
	"hy2://",
	"tuic://",
	"wireguard://",
	"socks://",
	"juicity://",
	"anytls://",
}

var zipExtensions = map[string]struct{}{
	".ovpn": {},
	".npv4": {},
	".ehi":  {},
	".hc":   {},
	".hat":  {},
	".sip":  {},
	".nm":   {},
	".zip":  {},
}

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

	summary := Summary{
		Protocols: map[string]int{},
		Formats:   map[string]int{},
	}
	paths := make([]string, 0)
	if err := filepath.WalkDir(outputDir, func(name string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if name == outputDir {
			return nil
		}
		if entry.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("symlink output forbidden: %s", name)
		}
		if entry.IsDir() {
			return nil
		}
		paths = append(paths, name)
		return nil
	}); err != nil {
		return Summary{}, err
	}
	sort.Strings(paths)
	if len(paths) == 0 {
		return Summary{}, errors.New("no output artifacts found")
	}

	for _, name := range paths {
		payload, err := os.ReadFile(name)
		if err != nil {
			return Summary{}, err
		}
		if len(payload) == 0 {
			return Summary{}, fmt.Errorf("empty output artifact: %s", name)
		}
		if err := validate(name, payload, &summary); err != nil {
			return Summary{}, err
		}
		relative, err := filepath.Rel(outputDir, name)
		if err != nil {
			return Summary{}, err
		}
		destination := filepath.Join(stage, relative)
		if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
			return Summary{}, err
		}
		if err := os.WriteFile(destination, payload, 0o600); err != nil {
			return Summary{}, err
		}
		summary.Files++
		summary.TotalSize += int64(len(payload))
	}

	manifestPath := filepath.Join(stage, "manifest.json")
	candidates, err := releasemanifest.Discover(stage, manifestPath)
	if err != nil {
		return Summary{}, err
	}
	manifest, err := releasemanifest.Build(stage, candidates)
	if err != nil {
		return Summary{}, err
	}
	if err := releasemanifest.WriteAtomic(manifestPath, manifest); err != nil {
		return Summary{}, err
	}
	if err := releasemanifest.Verify(stage, manifest); err != nil {
		return Summary{}, err
	}
	return summary, promoteDirectory(stage, filepath.Join(dataDir, "dist"))
}

func validate(name string, payload []byte, summary *Summary) error {
	lower := strings.ToLower(name)
	summary.Formats[formatName(lower)]++
	if strings.HasSuffix(lower, ".json") {
		var value any
		if err := json.Unmarshal(payload, &value); err != nil {
			return fmt.Errorf("invalid JSON output %s: %w", name, err)
		}
	}
	if _, ok := zipExtensions[filepath.Ext(lower)]; ok {
		reader, err := zip.OpenReader(name)
		if err != nil {
			return fmt.Errorf("invalid ZIP output %s: %w", name, err)
		}
		return reader.Close()
	}
	text := strings.TrimSpace(string(payload))
	if decoded, err := decodeBase64(text); err == nil && strings.Contains(string(decoded), "://") {
		text = string(decoded)
	}
	for _, line := range strings.Split(text, "\n") {
		trimmed := strings.TrimSpace(line)
		for _, scheme := range proxySchemes {
			if strings.HasPrefix(trimmed, scheme) {
				protocol := strings.TrimSuffix(scheme, "://")
				summary.Protocols[protocol]++
				if scheme == "vmess://" {
					summary.VmessCount++
				}
				break
			}
		}
	}
	return nil
}

func formatName(lower string) string {
	switch {
	case strings.HasSuffix(lower, ".decoded.json"):
		return "decoded.json"
	case strings.HasSuffix(lower, ".b64sub"):
		return "b64sub"
	default:
		if ext := filepath.Ext(lower); ext != "" {
			return ext
		}
		return "unknown"
	}
}

func decodeBase64(value string) ([]byte, error) {
	value = strings.TrimSpace(value)
	return base64.StdEncoding.DecodeString(value + strings.Repeat("=", (4-len(value)%4)%4))
}

func promoteDirectory(stage, target string) error {
	backup := target + ".backup"
	if err := os.RemoveAll(backup); err != nil {
		return err
	}
	hadOld := false
	if _, err := os.Stat(target); err == nil {
		if err := os.Rename(target, backup); err != nil {
			return err
		}
		hadOld = true
	} else if !os.IsNotExist(err) {
		return err
	}
	if err := os.Rename(stage, target); err != nil {
		if hadOld {
			_ = os.Rename(backup, target)
		}
		return err
	}
	if hadOld {
		return os.RemoveAll(backup)
	}
	return nil
}
