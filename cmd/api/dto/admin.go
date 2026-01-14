package dto

import "time"

// PaginationAdminUserDTO is the paginated response for admin user list.
// Uses UserProfileDTO which already includes credits field.
type PaginationAdminUserDTO struct {
	Total int              `json:"total"`
	Items []UserProfileDTO `json:"items"`
}

// GrantCreditRequestDTO is the request body from frontend for admin credit grant.
// Only requires amount and expiration; source/reason are set by handler.
type GrantCreditRequestDTO struct {
	Amount    int    `json:"amount" binding:"required,min=1"`
	ExpiredAt string `json:"expired_at" binding:"required"` // ISO8601 format
}

// GrantCreditInternalRequest is the internal request sent to User Service.
// Handler fills in source and reason automatically.
type GrantCreditInternalRequest struct {
	Amount    int    `json:"amount"`
	Source    string `json:"source"`
	Reason    string `json:"reason"`
	ExpiredAt string `json:"expired_at"`
}

// GrantCreditResponseDTO is the response after granting credits.
type GrantCreditResponseDTO struct {
	UserCode  string    `json:"user_code"`
	Amount    int       `json:"amount"`
	ExpiresAt time.Time `json:"expires_at"`
}

// CreatePostResponseDTO is explicitly defined for Swagger (previously generic object).
type CreatePostResponseDTO struct {
	Message string `json:"message"`
	PostID  string `json:"post_id"`
}
