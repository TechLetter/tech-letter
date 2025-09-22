package renderer

import (
	"context"
	"time"

	"github.com/chromedp/chromedp"
)

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"

func RenderHTML(url string) (string, error) {

	opts := append(chromedp.DefaultExecAllocatorOptions[:],
		chromedp.ExecPath("/usr/bin/chromium-browser"),
		chromedp.UserAgent(USER_AGENT),
		chromedp.Flag("no-sandbox", true),
		chromedp.Flag("disable-gpu", true),
		chromedp.Flag("disable-dev-shm-usage", true),
		chromedp.Flag("disable-crashpad", true),
		chromedp.Flag("disable-breakpad", true),
		chromedp.Flag("no-first-run", true),
		chromedp.Flag("no-default-browser-check", true),
		chromedp.Flag("disable-extensions", true),
		chromedp.Flag("user-data-dir", "/tmp/chrome-data"),
		chromedp.Flag("headless", true),
	)
	allocCtx, cancel := chromedp.NewExecAllocator(context.Background(), opts...)
	defer cancel()
	ctx, cancel := chromedp.NewContext(allocCtx)
	defer cancel()
	// Overall timeout for rendering
	ctx, cancel = context.WithTimeout(ctx, 30*time.Second)
	defer cancel()

	var htmlContent string
	err := chromedp.Run(ctx,
		chromedp.Navigate(url),
		// Wait until body is attached and ready
		chromedp.WaitReady("body", chromedp.ByQuery),
		// Short settle time for late JS
		chromedp.Sleep(1*time.Second),
		chromedp.OuterHTML("html", &htmlContent),
	)
	if err != nil {
		return "", err
	}
	return htmlContent, nil
}
