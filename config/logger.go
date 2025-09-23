package config

import (
	"log/slog"
	"os"
	"strings"
)

type _Logger interface {
	Debug(msg string, args ...any)
	Info(msg string, args ...any)
	Warn(msg string, args ...any)
	Error(msg string, args ...any)
	With(args ...any) _Logger
}

func Logger() _Logger {
	level := GetConfig().Logging.Level
	switch strings.ToLower(level) {
	case "debug":
		return NewLogger(slog.LevelDebug)
	case "info":
		return NewLogger(slog.LevelInfo)
	case "warn":
		return NewLogger(slog.LevelWarn)
	case "error":
		return NewLogger(slog.LevelError)
	default:
		return NewLogger(slog.LevelInfo)
	}
}

type slogLogger struct {
	logger *slog.Logger
}

func NewLogger(level slog.Level) _Logger {
	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: level})
	return &slogLogger{logger: slog.New(handler)}
}

func (l *slogLogger) Debug(msg string, args ...any) {
	l.logger.Debug(msg, args...)
}

func (l *slogLogger) Info(msg string, args ...any) {
	l.logger.Info(msg, args...)
}

func (l *slogLogger) Warn(msg string, args ...any) {
	l.logger.Warn(msg, args...)
}

func (l *slogLogger) Error(msg string, args ...any) {
	l.logger.Error(msg, args...)
}

func (l *slogLogger) With(args ...any) _Logger {
	return &slogLogger{logger: l.logger.With(args...)}
}
