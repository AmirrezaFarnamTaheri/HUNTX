# HuntX Telegram Configs Collector (Go)

A Go implementation of the Telegram configs collector that fetches proxy configurations from Telegram channels.

**Note:** This project fetches proxy configurations from public Telegram channels.

## Features

- 🚀 Fetches new messages from Telegram channels since last update
- 🔍 Extracts proxy configurations (Shadowsocks, Trojan, Vmess, Vless, Reality, Tuic, Hysteria, Juicity)
- 🧹 Removes duplicates automatically
- 💾 Saves all collected configs to a single file
- 📅 Tracks last update timestamp
- ⚡ High performance with goroutines support
- 🔗 **Working Config Testing** - Validates configurations by testing TCP connectivity to ensure ports are open

## Installation

1. Make sure you have Go installed (1.21+)
2. Install dependencies:
```bash comment
go mod tidy
```

3. Make sure you have the required files:
- `telegram_channels.json` - List of Telegram channels to monitor
- `last_update.txt` - Will be created automatically on first run

## Usage

Run the collector:
```bash
go run main.go
```

Or build and run:
```bash
go build -o huntx-collector main.go
./huntx-collector
```

## Files

- `main.go` - Main collector script
- `go.mod` - Go module definition
- `telegram_channels.json` - List of Telegram channels to scrape
- `last_update.txt` - Timestamp of last successful run
- `collected_configs.txt` - Output file with all collected configs
- `ir_configs.txt` - Working Iranian proxy configurations
- `irb64.txt` - Base64 encoded Iranian proxy configurations

## Configuration

Edit `telegram_channels.json` to add or remove channels you want to monitor.

## Output

All collected proxy configurations are saved to `collected_configs.txt`, one per line.

## Dependencies

- `github.com/PuerkitoBio/goquery` - HTML parsing
- `golang.org/x/net` - HTTP utilities

## Notes

- The script respects rate limits with 1-second delays between channel requests
- Only processes messages newer than the last update timestamp
- Automatically removes duplicate configurations
- Handles various proxy protocol formats
- **Working Config Testing**: Validates configurations by testing TCP connectivity with 1-second timeouts to ensure ports are accessible

## Performance

Go version offers:
- ⚡ Faster execution than Node.js
- 🧵 Concurrent processing capabilities
- 💾 Lower memory usage
- 🔒 Type safety

## Example Output

```
ss://efacffac-6e04-450d-aeb3-397ce072ab0e@91.99.58.127:2090?security=reality&...
vless://fe837fd0-840d-4cee-9334-0dc6c2b15c1c@5.181.20.219:17422?security=reality&...
vmess://eyJhZGQiOiI5MS45OS4xODUuMjE2IiwiYWlkIjoiMCIs...
```
