package eventbus

import "testing"

func TestAllTopicsIncludesEmbeddingDeleteRequested(t *testing.T) {
	want := TopicPostEmbeddingDeleteRequested.Base()

	for _, topic := range AllTopics {
		if topic.Base() == want {
			return
		}
	}

	t.Fatalf("AllTopics does not include %s", want)
}
