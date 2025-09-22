package parser_test

import (
	"tech-letter/parser"
	"tech-letter/renderer"
	"testing"
)

var testPostUrls = []string{
	"https://tech.kakao.com/posts/770",
	"https://techblog.woowahan.com/22396/",
}

func TestParseArticleOfHTML(t *testing.T) {
	for _, url := range testPostUrls {
		renderedHtml, err := renderer.RenderHTML(url)
		if err != nil {
			t.Fatalf("failed to render HTML: %v", err)
		}

		article, err := parser.ParseArticleOfHTML(renderedHtml)
		if err != nil {
			t.Fatalf("failed to parse article: %v", err)
		}

		t.Logf("Top Image: %s", article.TopImage)
	}
}
