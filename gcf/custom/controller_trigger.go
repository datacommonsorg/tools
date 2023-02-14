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
package custom

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
	ControllerTriggerFile = "trigger.txt"
)

// topicName is the full PubSub topic name in the following format
// projects/<project id>/topics/<topic id>
func getTopicInfo(topicName string) (
	string, string, error,
) {
	parts := strings.Split(topicName, "/")
	if len(parts) < 3 {
		return "", "", fmt.Errorf("invalid topicName: %s", topicName)
	}
	return parts[1], parts[3], nil
}

// Publish publishes the current import config to a topic.
func Publish(ctx context.Context, topicName string, attributes map[string]string) error {
	log.Printf("Publishing to topic: %s, for the following attributes\n: %s", topicName, attributes)
	projectID, topicID, err := getTopicInfo(topicName)
	if err != nil {
		return err
	}
	client, err := pubsub.NewClient(ctx, projectID)
	if err != nil {
		return err
	}
	defer client.Close()

	t := client.Topic(topicID)
	res := t.Publish(ctx, &pubsub.Message{
		Attributes: attributes,
	})

	id, err := res.Get(ctx)
	if err != nil {
		return errors.Wrap(err, "Failed to verify import notification msg was published")
	}
	log.Printf("PubSub import notification published with server generated msg id: %v\n", id)
	return nil
}
