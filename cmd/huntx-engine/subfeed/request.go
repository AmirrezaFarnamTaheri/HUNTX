package subfeed

import (
	"encoding/json"
	"errors"
	"io"
)

const maxRequestBytes = 16 * 1024

// Request carries source URL and validators over stdin, not process arguments.
type Request struct {
	URL          string `json:"url"`
	ETag         string `json:"etag,omitempty"`
	LastModified string `json:"last_modified,omitempty"`
}

func DecodeRequest(input io.Reader) (Request, error) {
	var request Request
	dec := json.NewDecoder(io.LimitReader(input, maxRequestBytes+1))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&request); err != nil {
		return Request{}, errors.New("invalid feed request")
	}
	var extra any
	if err := dec.Decode(&extra); err != io.EOF {
		return Request{}, errors.New("unexpected trailing feed input")
	}
	if len(request.URL) > 8192 || len(request.ETag) > 512 || len(request.LastModified) > 512 {
		return Request{}, errors.New("feed request exceeds field limits")
	}
	if _, err := ValidateURL(request.URL); err != nil {
		return Request{}, errors.New("feed source is not approved")
	}
	return request, nil
}
