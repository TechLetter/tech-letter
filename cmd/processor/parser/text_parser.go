package parser

import (
	"strings"

	"github.com/go-shiori/go-readability"
	"github.com/markusmobius/go-trafilatura"
	"golang.org/x/net/html"
)

// main parser
func ParseHtmlWithReadability(htmlStr string) (string, error) {
	doc, err := html.Parse(strings.NewReader(htmlStr))
	if err != nil {
		return "", err
	}

	article, err := readability.FromDocument(doc, nil)
	if err != nil {
		return "", err
	}
	return article.TextContent, nil
}

// 실험중인 parser
func ParseHtmlWithTrafilatura(htmlStr string) (string, error) {
	opts := trafilatura.Options{
		IncludeImages: true,
	}

	article, err := trafilatura.Extract(strings.NewReader(htmlStr), opts)
	if err != nil {
		return "", err
	}

	return article.ContentText, nil
}
