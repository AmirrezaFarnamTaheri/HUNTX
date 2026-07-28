package outputverify

import (
	"archive/zip"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type Summary struct {
	Files       int            `json:"files"`
	TotalSize   int64          `json:"total_size"`
	Protocols   map[string]int `json:"protocols"`
	Formats     map[string]int `json:"formats"`
	VmessCount  int            `json:"vmess_count"`
}

var proxySchemes = []string{"vmess://", "vless://", "trojan://", "ss://", "ssr://", "hysteria2://", "hy2://", "tuic://", "wireguard://"}

func Verify(dataDir string) (Summary, error) {
	outputDir := filepath.Join(dataDir, "outputs")
	if info, err := os.Stat(outputDir); err != nil || !info.IsDir() {
		return Summary{}, errors.New("output directory does not exist")
	}
	summary := Summary{Protocols: map[string]int{}, Formats: map[string]int{}}
	return summary, walk(outputDir, dataDir, summary)
}

func walk(outputDir, dataDir string, summary Summary) (Summary, error) {
	dist := filepath.Join(dataDir, "dist")
	stage, err := os.MkdirTemp(dataDir, ".dist-stage-")
	if err != nil { return summary, err }
	defer os.RemoveAll(stage)
	err = filepath.Walk(outputDir, func(name string, info os.FileInfo, err error) error {
		if err != nil { return err }
		if info.IsDir() { return nil }
		if info.Mode()&os.ModeSymlink != 0 { return fmt.Errorf("symlink: %s", name) }
		payload, err := os.ReadFile(name)
		if err != nil { return err }
		summary.Files++
		summary.TotalSize += int64(len(payload))
		summary.Formats[filepath.Ext(name)]++
		text := string(payload)
		for _, scheme := range proxySchemes {
			if strings.Contains(text, scheme) { summary.Protocols[strings.TrimSuffix(scheme, "://")]++ }
		}
		if strings.HasPrefix(text, "vmess://") { summary.VmessCount++ }
		if filepath.Ext(name)==".zip" { if _, err := zip.OpenReader(name); err != nil { return err } }
		if filepath.Ext(name)==".json" { var v any; if err:=json.Unmarshal(payload,&v); err!=nil{return err} }
		if filepath.Ext(name)==".b64sub" { _,err:=base64.StdEncoding.DecodeString(strings.TrimSpace(text)); if err!=nil{return err} }
		return os.WriteFile(filepath.Join(stage, filepath.Base(name)), payload, 0600)
	})
	if err != nil { return summary, err }
	_ = os.RemoveAll(dist)
	if err:=os.Rename(stage, dist); err!=nil{return summary,err}
	return summary,nil
}
