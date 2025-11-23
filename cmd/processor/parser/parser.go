package parser

import (
	"strings"

	"github.com/go-shiori/go-readability"
	"golang.org/x/net/html"
)

type ParsedArticle struct {
	HtmlContent      string
	PlainTextContent string
	TopImage         string
}

func ParseArticleOfHTML(htmlStr string) (*ParsedArticle, error) {
	doc, err := html.Parse(strings.NewReader(htmlStr))
	if err != nil {
		return nil, err
	}

	article, err := readability.FromDocument(doc, nil)
	if err != nil {
		return nil, err
	}
	return &ParsedArticle{
		HtmlContent:      article.Content,
		PlainTextContent: article.TextContent,
		TopImage:         article.Image,
	}, nil
}
