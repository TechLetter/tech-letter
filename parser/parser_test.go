package parser_test

import (
	"tech-letter/parser"
	"tech-letter/renderer"
	"testing"

	"github.com/stretchr/testify/assert"
)

var testPostUrls = []string{
	"https://tech.kakao.com/posts/721",          // 카카오 MySQL InnoDB Log에 대한 이해 - (1) - tech.kakao.com
	"https://tech.kakaopay.com/post/pink-ward/", // 카카오 페이 Pink Ward - tech.kakaopay.com
	"https://d2.naver.com/helloworld/5215257",   // 네이버 오브젝트 스토리지를 활용하는 HDFS 호환 분산 파일 시스템 - d2.naver.com
}

func TestParseArticleOfHTML(t *testing.T) {
	for _, url := range testPostUrls {
		renderedHtml, err := renderer.RenderHTML(url)
		assert.NoError(t, err)
		assert.NotEmpty(t, renderedHtml)

		article, err := parser.ParseArticleOfHTML(renderedHtml)
		if err != nil {
			t.Errorf("failed to parse article: %v", err)
		}
		assert.NotNil(t, article)
		assert.NotEmpty(t, article.HtmlContent)
		assert.NotEmpty(t, article.PlainTextContent)

		t.Logf("Top Image: %s", article.TopImage)
	}
}
