package parser_test

import (
	"tech-letter/cmd/processor/parser"
	"tech-letter/cmd/processor/renderer"
	"testing"
)

var testPostUrls = []string{
	"https://tech.kakao.com/posts/770",
	"https://techblog.woowahan.com/22396/",
	"https://microservices.io//post/genaidevelopment/2025/09/10/allow-git-commit-considered-harmful.html",
	"https://techblog.gccompany.co.kr/%EA%B8%B0%EC%88%A0%EC%9D%84-%EA%B8%B0%ED%9A%8D%ED%95%98%EC%A7%80-%EC%95%8A%EB%8A%94-%EA%B8%B0%EC%88%A0%EA%B8%B0%ED%9A%8D%ED%8C%80-dae25aadd69b",
	"https://d2.naver.com/helloworld/3088532",
	"https://techblog.lycorp.co.jp/ko/techniques-for-improving-code-quality-23",
}

func TestParseArticleWithReadability(t *testing.T) {
	for _, url := range testPostUrls {
		t.Logf("Processing URL: %s", url)
		renderedHtml, err := renderer.RenderHTML(url)
		if err != nil {
			t.Logf("failed to render HTML: %v", err)
		} else {
			article, err := parser.ParseHtmlWithReadability(renderedHtml)
			if err != nil {
				t.Logf("failed to parse article: %v", err)
			} else {
				if article.TopImage == "" {
					t.Log("top image is empty")
				} else {
					t.Logf("Top Image: %s", article.TopImage)
				}
			}
		}
	}
}

func TestParseArticleWithTrafilatura(t *testing.T) {
	for _, url := range testPostUrls {
		t.Logf("Processing URL: %s", url)
		renderedHtml, err := renderer.RenderHTML(url)
		if err != nil {
			t.Logf("failed to render HTML: %v", err)
		} else {
			article, err := parser.ParseHtmlWithTrafilatura(renderedHtml)
			if err != nil {
				t.Logf("failed to parse article: %v", err)
				t.Logf("article content: %s", renderedHtml)
			} else {
				if article.TopImage == "" {
					t.Log("top image is empty")
				} else {
					t.Logf("Top Image: %s", article.TopImage)
				}
			}
		}
	}
}

func TestParseArticleWithGoose(t *testing.T) {
	for _, url := range testPostUrls {
		t.Logf("Processing URL: %s", url)
		renderedHtml, err := renderer.RenderHTML(url)
		if err != nil {
			t.Logf("failed to render HTML: %v", err)
		} else {
			article, err := parser.ParseHtmlWithGoose(renderedHtml)
			if err != nil {
				t.Logf("failed to parse article: %v", err)
			} else {
				if article.TopImage == "" {
					t.Log("top image is empty")
				} else {
					t.Logf("Top Image: %s", article.TopImage)
				}
			}
		}
	}
}
