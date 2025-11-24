package renderer_test

import (
	"tech-letter/cmd/processor/parser"
	"tech-letter/cmd/processor/renderer"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestRenderHTML(t *testing.T) {
	url := "https://www.44bits.io/ko/post/easy-deploy-with-docker"
	html, err := renderer.RenderHTML(url)
	if err != nil {
		t.Logf("Failed to render HTML: %v", err)
		return
	}

	article, err := parser.ParseHtmlWithReadability(html)
	if err != nil {
		t.Logf("Failed to parse article: %v", err)
		return
	}
	assert.Greater(t, len(article.PlainTextContent), 60000)
}
