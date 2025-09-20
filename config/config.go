package config

import (
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

const CONFIG_FILE = "config.yaml"

type AppConfig struct {
	GeminiApiKey string `yaml:"gemini_api_key"`
	GeminiModel  string `yaml:"gemini_model"`
}

var config *AppConfig

func InitApp() {
	data, err := os.ReadFile(filepath.Join(GetBasePath(), CONFIG_FILE))
	if err != nil {
		panic(err)
	}

	var c AppConfig
	err = yaml.Unmarshal(data, &c)
	if err != nil {
		panic(err)
	}
	config = &c
}

func GetConfig() AppConfig {
	if config == nil {
		InitApp()
	}

	return *config
}

func GetBasePath() string {
	cwd, err := os.Getwd()
	if err != nil {
		return ""
	}

	dir := cwd
	for {
		cfgPath := filepath.Join(dir, CONFIG_FILE)
		if info, err := os.Stat(cfgPath); err == nil && !info.IsDir() {
			return dir
		}

		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}

	return ""
}
