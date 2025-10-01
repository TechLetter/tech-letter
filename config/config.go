package config

import (
	"os"
	"path/filepath"

	"github.com/joho/godotenv"
	"gopkg.in/yaml.v3"
)

const ENV_FILE = ".env"
const CONFIG_FILE = "config.yaml"

type AppConfig struct {
	Logging            LoggingConfig `yaml:"logging"`
	GeminiModel        string        `yaml:"gemini_model"`
	BlogFetchBatchSize int           `yaml:"blog_fetch_batch_size"`
	Blogs              []BlogSource  `yaml:"blogs"`
}

type LoggingConfig struct {
	Level string `yaml:"level"`
}

// BlogSource is a single blog configuration item
type BlogSource struct {
	Name     string `yaml:"name"`
	URL      string `yaml:"url"`
	RSSURL   string `yaml:"rss_url"`
	BlogType string `yaml:"blog_type"`
}

var config *AppConfig

func InitApp() {
	// load environment variables
	godotenv.Load(filepath.Join(GetBasePath(), ENV_FILE))

	// load configuration file
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
