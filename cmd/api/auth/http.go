package auth

import (
	"errors"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

var (
	ErrMissingHeader = errors.New("missing_authorization_header")
	ErrInvalidFormat = errors.New("invalid_authorization_header")
	ErrEmptyToken    = errors.New("empty_token")
)

// ExtractBearerToken extracts the Bearer token from the Authorization header.
func ExtractBearerToken(c *gin.Context) (string, error) {
	authHeader := c.GetHeader("Authorization")
	if authHeader == "" {
		return "", ErrMissingHeader
	}

	parts := strings.SplitN(authHeader, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
		return "", ErrInvalidFormat
	}

	token := strings.TrimSpace(parts[1])
	if token == "" {
		return "", ErrEmptyToken
	}

	return token, nil
}

// AbortWithUnauthorized aborts the request with 401 status and error JSON.
func AbortWithUnauthorized(c *gin.Context, err error) {
	c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": err.Error()})
}
