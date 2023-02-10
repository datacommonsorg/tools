// Copyright 2023 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//	https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
package gcf

import (
	"context"
	"fmt"
	"log"
	"strings"

	"cloud.google.com/go/pubsub"
	"github.com/pkg/errors"
)

const (
	dcManifestPath        = "/memfile/core_resolved_mcfs_memfile/core_resolved_mcfs.binarypb"
	controllerTriggerFile = "trigger.txt"
)

type PublishConfig struct {
	// TopicName is the full PubSub topic name in the following format
	// projects/<project id>/topics/<topic id>
	TopicName string
}

func (p PublishConfig) ProjectID() string {
	return strings.Split(p.TopicName, "/")[1]
}

func (p PublishConfig) TopicID() string {
	return strings.Split(p.TopicName, "/")[3]
}

type CustomDCPubSubMsg struct {
	importName               string
	dcManifestPath           string
	customManifestPath       string
	bigstoreDataDirectory    string
	bigstoreCacheDirectory   string
	bigstoreControlDirectory string
}

func (s CustomDCPubSubMsg) String() string {
	return fmt.Sprintf(`import_name=%s,\
dc_manifest_path=%s,\
custom_manifest_path=%s,\
bigstore_data_directory=%s,\
bigstore_cache_directory=%s,\
bigstore_control_directory=%s,\
`,
		s.importName,
		s.dcManifestPath,
		s.customManifestPath,
		s.bigstoreDataDirectory,
		s.bigstoreCacheDirectory,
		s.bigstoreControlDirectory,
	)
}

func (s CustomDCPubSubMsg) Attributes() map[string]string {
	return map[string]string{
		"import_name":                s.importName,
		"dc_manifest_path":           s.dcManifestPath,
		"custom_manifest_path":       s.customManifestPath,
		"bigstore_data_directory":    s.bigstoreDataDirectory,
		"bigstore_cache_directory":   s.bigstoreCacheDirectory,
		"bigstore_control_directory": s.bigstoreControlDirectory,
	}
}

// Publish publishes the current import config to a topic.
func (s CustomDCPubSubMsg) Publish(ctx context.Context, p PublishConfig) error {
	client, err := pubsub.NewClient(ctx, p.ProjectID())
	if err != nil {
		return err
	}
	defer client.Close()

	msg := s.String()
	log.Printf("Publishing the following message: %s", msg)

	t := client.Topic(p.TopicID())
	res := t.Publish(ctx, &pubsub.Message{
		Attributes: s.Attributes(),
	})

	id, err := res.Get(ctx)
	if err != nil {
		return errors.Wrap(err, "Failed to verify import notification msg was published")
	}
	log.Printf("PubSub import notification published with server generated msg id: %v\n", id)
	return nil
}
