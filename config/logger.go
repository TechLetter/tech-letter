package config

import (
	"strings"

	"github.com/gookit/slog"
	"github.com/gookit/slog/handler"
)

type _Logger interface {
	Debug(args ...any)
	Info(args ...any)
	Warn(args ...any)
	Error(args ...any)
	Debugf(format string, args ...any)
	Infof(format string, args ...any)
	Warnf(format string, args ...any)
	Errorf(format string, args ...any)
}

var Logger _Logger

func InitLogger(logging LoggingConfig) {
	level := strings.ToLower(logging.Level)
	switch level {
	case "debug", "info", "warn", "error":
		Logger = NewLogger(level)
	default:
		Logger = NewLogger("info")
	}
}

func NewLogger(level string) _Logger {
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
