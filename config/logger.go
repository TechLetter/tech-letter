package config

import (
	"strings"

	"github.com/gookit/slog"
	"github.com/gookit/slog/handler"
)

type _Logger interface {
	Debug(msg string)
	Info(msg string)
	Warn(msg string)
	Error(msg string)
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

type slogLogger struct {
	logger *slog.Logger
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
	return &slogLogger{logger: logger}
}

func (l *slogLogger) Debug(msg string) {
	l.logger.Debug(msg)
}

func (l *slogLogger) Info(msg string) {
	l.logger.Info(msg)
}

func (l *slogLogger) Warn(msg string) {
	l.logger.Warn(msg)
}

func (l *slogLogger) Error(msg string) {
	l.logger.Error(msg)
}

func (l *slogLogger) Debugf(format string, args ...any) {
	l.logger.Debugf(format, args...)
}

func (l *slogLogger) Infof(format string, args ...any) {
	l.logger.Infof(format, args...)
}

func (l *slogLogger) Warnf(format string, args ...any) {
	l.logger.Warnf(format, args...)
}

func (l *slogLogger) Errorf(format string, args ...any) {
	l.logger.Errorf(format, args...)
}
