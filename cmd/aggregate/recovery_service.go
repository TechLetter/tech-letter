package main

import (
	"tech-letter/cmd/aggregate/event/dispatcher"
	"tech-letter/db"
	"tech-letter/repositories"
)

// RecoveryService 는 미완료 포스트들에 대해 적절한 이벤트를 재발행하는 책임을 가진다.
type RecoveryService struct {
	postRepo        *repositories.PostRepository
	eventDispatcher *dispatcher.EventDispatcher
}

// NewRecoveryService 새로운 복구 서비스를 생성한다.
func NewRecoveryService(eventDispatcher *dispatcher.EventDispatcher) *RecoveryService {
	return &RecoveryService{
		postRepo:        repositories.NewPostRepository(db.Database()),
		eventDispatcher: eventDispatcher,
	}
}

// todo: rest api 엔드포인트와 연결해서 특정 포스트에 대해 재처리할 수 있도록 하기
// 예: POST /recovery/posts/{id} - 해당 포스트에 대해 재처리 이벤트 재발행
