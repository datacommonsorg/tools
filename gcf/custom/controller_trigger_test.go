// Copyright 2023 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package custom

import "testing"

func TestGetTopicInfo(t *testing.T) {
	for _, c := range []struct {
		topicName     string
		wantProjectID string
		wantTopicID   string
	}{
		{
			"projects/test-project-id/topics/test-topic-id",
			"test-project-id",
			"test-topic-id",
		},
	} {
		projectID, topicID, err := getTopicInfo(c.topicName)
		if err != nil {
			t.Errorf("getTopicInfo(%v) = %v", c, err)
			continue
		}
		if projectID != c.wantProjectID || topicID != c.wantTopicID {
			t.Errorf(
				"getTopicInfo() want %s, %s, got %s, %s",
				c.wantProjectID, c.wantTopicID, projectID, topicID)
		}
	}
}
