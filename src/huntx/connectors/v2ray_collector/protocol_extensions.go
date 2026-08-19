package main

import "regexp"

// init keeps the scraper's Hysteria2 matcher aligned with the official
// hysteria2:// and hy2:// share-link schemes. The original collector recognized
// only the short alias and silently missed the long form.
func init() {
	patterns["hysteria2"] = regexp.MustCompile(`(?:hy2|hysteria2)://[^\s<>#]+`)
}
