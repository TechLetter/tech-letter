package eventbus

// 전역 토픽 선언: 기능별 기본 토픽 이름을 관리합니다.
// 필요시 환경설정으로 교체할 수 있도록 한 곳에서 관리합니다.

var (
	TopicPostEvents = NewTopic("tech-letter.post.events")
)

var AllTopics = []Topic{
	TopicPostEvents,
}
