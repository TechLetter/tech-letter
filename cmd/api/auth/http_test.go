package auth

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestExtractBearerToken(t *testing.T) {
	gin.SetMode(gin.TestMode)

	testCases := []struct {
		name        string
		headerValue string
		wantToken   string
		wantErr     error
	}{
		{
			name:    "missing header",
			wantErr: ErrMissingHeader,
		},
		{
			name:        "invalid scheme",
			headerValue: "Basic abc",
			wantErr:     ErrInvalidFormat,
		},
		{
			name:        "missing token part",
			headerValue: "Bearer",
			wantErr:     ErrInvalidFormat,
		},
		{
			name:        "empty token",
			headerValue: "Bearer    ",
			wantErr:     ErrEmptyToken,
		},
		{
			name:        "valid bearer token",
			headerValue: "bearer token-123",
			wantToken:   "token-123",
		},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			ginCtx, _ := newTestGinContext(testCase.headerValue)

			token, err := ExtractBearerToken(ginCtx)
			if !errors.Is(err, testCase.wantErr) {
				t.Fatalf("expected error %v, got %v", testCase.wantErr, err)
			}
			if token != testCase.wantToken {
				t.Fatalf("expected token %q, got %q", testCase.wantToken, token)
			}
		})
	}
}

func TestAbortWithUnauthorized(t *testing.T) {
	gin.SetMode(gin.TestMode)

	ginCtx, recorder := newTestGinContext("")
	AbortWithUnauthorized(ginCtx, ErrInvalidFormat)

	if !ginCtx.IsAborted() {
		t.Fatalf("expected request to be aborted")
	}
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected status %d, got %d", http.StatusUnauthorized, recorder.Code)
	}

	var body map[string]string
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("failed to decode response body: %v", err)
	}
	if body["error"] != ErrInvalidFormat.Error() {
		t.Fatalf("expected error message %q, got %q", ErrInvalidFormat.Error(), body["error"])
	}
}

func newTestGinContext(authorizationHeader string) (*gin.Context, *httptest.ResponseRecorder) {
	recorder := httptest.NewRecorder()
	ginCtx, _ := gin.CreateTestContext(recorder)

	request := httptest.NewRequest(http.MethodGet, "/", nil)
	if authorizationHeader != "" {
		request.Header.Set("Authorization", authorizationHeader)
	}
	ginCtx.Request = request

	return ginCtx, recorder
}
