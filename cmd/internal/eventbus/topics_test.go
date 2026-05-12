package eventbus

import "testing"

func TestAllTopicsIncludesEmbeddingDeleteRequested(t *testing.T) {
	wants := []string{
		TopicPostEmbeddingDeleteRequested.Base(),
		TopicChatContextCompression.Base(),
	}

	for _, want := range wants {
		found := false
		for _, topic := range AllTopics {
			if topic.Base() == want {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("AllTopics does not include %s", want)
		}
	}
}
