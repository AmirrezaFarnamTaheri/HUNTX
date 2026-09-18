package releasemanifest

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"time"
)

// EmptyReleaseArtifact is a nonempty, digest-verified assertion from a successful
// build. Missing outputs and ordinary zero-byte artifacts remain invalid.
const EmptyReleaseArtifact = "empty-release.json"

type EmptyRelease struct {
	SchemaVersion int    `json:"schema_version"`
	Status        string `json:"status"`
	RecordCount   *int   `json:"record_count"`
	Reason        string `json:"reason"`
	GeneratedAt   string `json:"generated_at"`
	MinIngestedAt string `json:"min_ingested_at,omitempty"`
}

func ReadEmptyRelease(filePath string) (EmptyRelease, error) {
	payload, err := os.ReadFile(filePath)
	if err != nil {
		return EmptyRelease{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	var marker EmptyRelease
	if err := decoder.Decode(&marker); err != nil {
		return EmptyRelease{}, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return EmptyRelease{}, errors.New("empty release marker contains trailing data")
	}
	if marker.SchemaVersion != 1 || marker.Status != "success" || marker.RecordCount == nil ||
		*marker.RecordCount != 0 || marker.Reason != "no_eligible_records" {
		return EmptyRelease{}, errors.New("invalid intentional empty release marker")
	}
	generated, err := time.Parse(time.RFC3339Nano, marker.GeneratedAt)
	if err != nil {
		return EmptyRelease{}, errors.New("empty release requires original generated_at timestamp")
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(payload, &fields); err != nil {
		return EmptyRelease{}, err
	}
	if _, present := fields["min_ingested_at"]; present {
		start, err := time.Parse(time.RFC3339Nano, marker.MinIngestedAt)
		if err != nil || start.After(generated) {
			return EmptyRelease{}, errors.New("invalid empty release window start")
		}
	}
	return marker, nil
}

func IsEmptyRelease(manifest Manifest) bool {
	return manifest.ArtifactCount == 1 && len(manifest.Artifacts) == 1 &&
		manifest.Artifacts[0].Path == EmptyReleaseArtifact
}

func validateEmptyRelease(root string, artifacts []Artifact) error {
	for _, artifact := range artifacts {
		if artifact.Path != EmptyReleaseArtifact {
			continue
		}
		if len(artifacts) != 1 {
			return errors.New("intentional empty release cannot contain other artifacts")
		}
		_, err := ReadEmptyRelease(filepath.Join(root, EmptyReleaseArtifact))
		return err
	}
	return nil
}
