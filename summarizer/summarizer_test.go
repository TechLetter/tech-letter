package summarizer_test

import (
	"tech-letter/config"
	"tech-letter/summarizer"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestSummarizeText(t *testing.T) {

	config.InitApp()

	text := `1. 저장 비용 증가
AI 개발을 위해서는 지속적으로 늘어나는 데이터를 비용 효율적으로 저장해야 합니다. 모델 개선과 재학습을 위해 원본 데이터를 장기간 보존해야 하는 경우도 생깁니다.
그러나 Hadoop은 컴퓨팅과 스토리지가 강하게 결합되어 있어 스토리지만 독립적으로 확장하기 어렵습니다. 컴퓨팅 수요가 없는 상태에서 스토리지 공간을 확보하기 위해 노드를 추가하면 비용이 낭비될 수 있습니다. 또한, HDFS는 기본적으로 3중 복제(replication)를 유지해야 하므로 저장 비용 부담이 큽니다.
2. 파일 개수 제한
AI 개발에는 이미지, 음성, 텍스트 등 수천만 개의 작은 파일이 사용됩니다.
HDFS에는 잘 알려진 작은 파일 문제가 있습니다. 이는 모든 파일과 블록의 메타데이터가 네임노드 메모리에 저장되기 때문입니다. 예를 들어 1천만 개의 파일을 관리하려면 약 3GB의 메모리가 필요합니다. 결국 HDFS에서 관리할 수 있는 파일 개수는 단일 네임노드 메모리 용량에 의해 제한됩니다.
3. 데이터센터 재해 대응 취약
HDFS는 일반적으로 단일 데이터센터의 노드들로 구성됩니다. 데이터센터 장애나 재해에 대비하려면 타 데이터센터로 데이터를 복제하는 별도의 설루션이 필요하며 이로 인해 추가 비용이 발생합니다.
4. 운영 비용 증가
네이버는 전문 인력이 공용 Hadoop 클러스터를 운영하고 있어 상대적으로 부담이 적지만, 일반적으로 Hadoop 클러스터 구축과 운영은 매우 복잡하고 비용이 큽니다. 개별적으로 안정적인 Hadoop 환경을 구축,운영하려면 전문 지식과 높은 유지 비용이 필요합니다.
5. Kubernetes에서 낮은 사용성
네이버 AI 플랫폼은 Kubernetes 기반으로 구축되어 있으며, GPU 지원과 함께 Kubeflow, KServe 등 다양한 AI 오픈소스를 활용합니다.
하지만 HDFS는 POSIX API와 CSI 드라이버를 지원하지 않기 때문에 Kubernetes의 일반적인 스토리지 사용 방식인 PersistentVolume으로 사용할 수 없습니다. 따라서 HDFS를 Kubernetes에서 사용하려면 컨테이너에 Hadoop 패키지, 설정, 인증 정보를 준비하고 HDFS API로 코드를 작성해야 합니다. 이는 매우 번거롭고 AI 개발의 생산성을 저하시킵니다.
오브젝트 스토리지의 이점
Hadoop은 데이터 로컬리티를 통해 높은 성능을 제공하지만, 이로 인해 컴퓨팅과 스토리지 리소스를 분리하기 어렵습니다. HDFS는 컴퓨팅 노드와 결합되어 운영되므로, 단순히 저장 공간(HDFS)을 확장하려 해도 추가 Hadoop 노드를 투입해야 합니다.
반면, 클라우드 환경에서는 컴퓨팅과 스토리지를 독립적으로 확장할 수 있습니다.
`

	summary, log, err := summarizer.SummarizeText(text)
	assert.NoError(t, err)
	assert.NotEmpty(t, summary.SummaryShort)
	assert.NotEmpty(t, summary.SummaryLong)
	assert.NotEmpty(t, summary.Categories)
	assert.NotEmpty(t, summary.Tags)
	assert.Nil(t, summary.Error)

	t.Log(summary.SummaryShort)
	t.Log(summary.Categories)
	t.Log(summary.Tags)
	t.Log(log)
}
