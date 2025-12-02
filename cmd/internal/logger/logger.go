package logger

import (
	"os"
	"strings"

	"github.com/gookit/slog"
	"github.com/gookit/slog/handler"
)

// Logger 는 애플리케이션 전역에서 사용하는 최소 로거 인터페이스다.
// 필요 시 다른 구현으로 교체할 수 있도록 인터페이스로 노출한다.
type Logger interface {
	Debug(args ...any)
	Info(args ...any)
	Warn(args ...any)
	Error(args ...any)
	Debugf(format string, args ...any)
	Infof(format string, args ...any)
	Warnf(format string, args ...any)
	Errorf(format string, args ...any)
}

// Log 는 전역 로거 인스턴스다.
// InitFromEnv 가 호출되지 않더라도 기본 info 레벨로 동작하도록 초기화한다.
var Log Logger = NewLogger("info")

// InitFromEnv 는 주어진 환경변수 키에서 로그 레벨을 읽어 전역 로거를 초기화한다.
// 값이 비어 있거나 지원하지 않는 경우 기본값으로 info 를 사용한다.
func InitFromEnv(envKey string) {
	level := strings.ToLower(os.Getenv(envKey))
	if level == "" {
		level = "info"
	}
	Log = NewLogger(level)
}

// NewLogger 는 주어진 레벨로 gookit/slog 기반 로거를 생성한다.
func NewLogger(level string) Logger {
	logLevel := slog.LevelByName(level)

	var levels slog.Levels
	for _, lv := range slog.AllLevels {
		if lv <= logLevel {
			levels = append(levels, lv)
		}
	}

	h := handler.NewConsoleHandler(levels)
	h.TextFormatter().EnableColor = true

	logger := slog.NewWithHandlers(h)
	return logger
}
