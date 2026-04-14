# **통합 커뮤니케이션 시스템(카카오톡-슬랙 연동) 제품 요구사항 및 기술 설계서**

## **1\. 프로젝트 배경, 목표 및 전략적 기대 효과**

현재 기업의 고객 커뮤니케이션 환경은 외부 고객을 향한 주요 소통 채널인 카카오톡 비즈니스 채널과, 내부 임직원 간의 업무 협업 및 정보 공유를 위한 슬랙(Slack) 플랫폼으로 이원화되어 운영되고 있다. 이러한 이종 플랫폼 간의 물리적, 논리적 분리 현상은 고객 상담 업무의 연속성을 심각하게 저해하는 근본적인 원인으로 지목되고 있다. 상담원은 카카오톡 관리자 센터 또는 별도의 채팅 솔루션 화면과 내부 협업을 위한 슬랙 화면을 지속적으로 번갈아 확인해야 하는 인지적 과부하(Cognitive Overload)를 겪고 있으며, 특정 고객의 문의 사항에 대해 유관 부서의 확인이 필요한 경우 해당 내용을 복사하여 슬랙으로 전달하고 답변을 받아 다시 카카오톡으로 옮겨 적는 비효율적인 수동 중계 작업을 수행하고 있다. 이는 필연적으로 고객 응답 시간(SLA)의 지연을 초래하며, 분절된 커뮤니케이션 채널로 인해 고객 상담 이력과 내부 의사결정 맥락이 통합적으로 관리되지 못하는 데이터 파편화 문제를 야기한다.

본 프로젝트의 핵심 목표는 카카오톡 채널 API와 슬랙 API를 양방향으로 연동하는 고성능 미들웨어 시스템을 구축하여, 슬랙이라는 단일 워크스페이스 내에서 고객의 카카오톡 메시지를 실시간으로 확인하고 즉각적으로 응대할 수 있는 완전한 통합 커뮤니케이션 환경(Unified Communication System)을 완성하는 것이다. 이를 통해 상담원은 친숙한 슬랙 인터페이스를 벗어나지 않고도 고객과 매핑된 1:1 전용 채널에서 대화를 이어나갈 수 있으며, 필요한 경우 해당 채널에 유관 부서 담당자를 초대하여 고객의 문의 맥락을 투명하게 공유하고 신속하게 문제를 해결할 수 있다. 본 설계서는 이러한 비즈니스 목표를 달성하기 위해 요구되는 상세 기획(요구 사항 정의, 기능 정의, 정책 설계), 백엔드 개발(FastAPI 기반), 그리고 서버, 데이터베이스, 인프라스트럭처 구성에 이르는 전 방위적인 과업 범위를 포괄하여 기술적 청사진을 제시한다.

## **2\. 핵심 아키텍처 구성 및 인프라스트럭처 설계**

본 통합 커뮤니케이션 시스템은 카카오톡 서버와 슬랙 서버 사이에서 발생하는 대규모 실시간 웹훅(Webhook) 및 이벤트 트래픽을 지연 없이 중계해야 하는 미션 크리티컬(Mission Critical) 애플리케이션이다. 따라서 높은 동시성 처리 능력, 시스템의 내결함성(Fault Tolerance), 그리고 각 플랫폼이 요구하는 엄격한 타임아웃 규정을 준수할 수 있는 아키텍처 설계가 필수적이다.

### **2.1. FastAPI 기반의 비동기 미들웨어 프레임워크**

백엔드 시스템의 핵심 프레임워크로는 Python 생태계에서 가장 우수한 성능을 자랑하는 FastAPI가 채택되었다. FastAPI는 ASGI(Asynchronous Server Gateway Interface) 표준인 Starlette을 기반으로 구축되어 노드(Node.js)나 고(Go) 언어에 필적하는 높은 비동기 처리 성능을 제공하며, Pydantic을 활용한 강력한 데이터 타입 힌팅 및 유효성 검사 기능을 통해 외부 API 연동 과정에서 발생할 수 있는 데이터 구조 오류를 컴파일 단계에서 원천 차단할 수 있다.1

이러한 FastAPI의 비동기(Async) 특성은 본 시스템과 같이 I/O 바운드(Network Input/Output Bound) 작업이 주를 이루는 환경에서 그 진가를 발휘한다.3 수천 명의 고객이 동시에 메시지를 발송하더라도, FastAPI는 스레드를 블로킹하지 않고 수많은 동시 연결을 효율적으로 처리할 수 있다. 미들웨어는 카카오톡이나 슬랙으로부터 웹훅 이벤트를 수신하면, Pydantic 모델을 통해 페이로드의 정합성을 즉각적으로 검증하고 200 OK 상태 코드를 반환하여 연결을 종료한 뒤, 실제 API 호출 로직은 백그라운드로 이관하는 방식으로 동작한다.2

### **2.2. 비동기 태스크 큐(Task Queue) 설계: Celery와 Redis의 결합**

FastAPI 자체적으로 BackgroundTasks 기능을 제공하여 동일한 이벤트 루프 내에서 가벼운 백그라운드 작업을 처리할 수 있으나, 본 프로젝트의 규모와 안정성 요구 수준에는 부합하지 않는다. BackgroundTasks는 웹 서버 프로세스에 종속되어 있어 애플리케이션이 크래시되거나 재시작될 경우 큐에 대기 중이던 모든 작업(고객 메시지 전송, 파일 다운로드 등)이 소멸되는 치명적인 데이터 유실 위험을 내포하고 있다.5 또한, 외부 네트워크 지연이나 대용량 미디어 파일 처리를 위한 CPU 집약적 작업이 메인 이벤트 루프를 점유할 경우 웹 서버 전체의 성능 저하를 유발할 수 있다.6

이를 극복하기 위해 시스템 아키텍처는 분산 태스크 큐 시스템인 Celery와 인메모리 데이터 스토어인 Redis를 메시지 브로커(Message Broker)로 도입하여 웹 서버와 워커(Worker) 프로세스를 물리적으로 분리하는 구조를 채택한다.3

| 컴포넌트 | 아키텍처 내 역할 및 작동 매커니즘 |
| :---- | :---- |
| **FastAPI Web Server** | 외부 웹훅 수신, Pydantic 스키마 검증, Redis 브로커로 태스크 직렬화 및 발행(Publish), 즉각적인 HTTP 응답 반환 |
| **Redis Message Broker** | FastAPI와 Celery 간의 메시지 전달 매개체, 고속 인메모리 큐잉, 처리 대기 중인 이벤트 데이터의 임시 영속성 보장 |
| **Celery Worker Nodes** | Redis 큐에서 태스크를 소비(Consume)하여 슬랙 API 호출, 파일 다운로드 및 업로드, 데이터베이스 트랜잭션 등 무거운 비즈니스 로직을 비동기적으로 병렬 처리 |

이러한 구조적 분리는 슬랙 API의 Rate Limit 초과 시 재시도(Retry) 로직을 안전하게 구현하고, 트래픽 폭증 시 워커 노드만을 독립적으로 수평 확장(Scale-out)할 수 있는 아키텍처적 유연성을 제공한다.

### **2.3. 인프라스트럭처 및 배포 환경: AWS ECS Fargate의 선정**

클라우드 배포 환경 구성 시 서버리스 함수 컴퓨팅 모델인 AWS Lambda와 컨테이너 오케스트레이션 서비스인 AWS ECS(Elastic Container Service) Fargate를 비교 분석하였으며, 결론적으로 ECS Fargate 환경이 본 프로젝트에 압도적으로 적합한 것으로 판명되었다.

가장 결정적인 이유는 콜드 스타트(Cold Start) 문제와 백그라운드 프로세싱의 지속성 때문이다. AWS Lambda는 요청이 없을 때 자원을 해제하여 비용을 절감하지만, 새로운 요청이 인입되어 컨테이너를 다시 구동하는 과정에서 1초에서 최대 3초에 이르는 지연 시간이 발생한다.8 카카오톡 웹훅 정책에 따르면 시스템은 반드시 3초 이내에 정상 응답을 반환해야 하며, 이를 초과할 경우 카카오 서버는 전송 실패로 간주하고 재시도 로직을 가동하여 중복 메시지를 발생시키거나 궁극적으로 웹훅 호출 자체를 차단하게 된다.4

또한 Lambda는 HTTP 응답을 반환한 직후 프로세스가 동결되므로, 응답 이후 Celery 워커 등을 활용해 비동기적으로 슬랙 API를 호출하고 파일을 전송하는 지속적인 백그라운드 처리가 불가능하다.9 반면 AWS ECS Fargate는 도커(Docker) 컨테이너 기반으로 상시 구동되어 콜드 스타트 지연이 전혀 없으며, 트래픽 증감에 따라 안정적인 자동 확장(Auto-scaling)을 지원하므로 대규모 실시간 양방향 통신 채널을 운영하는 데 최적화된 인프라를 제공한다.12

## **3\. 상세 기능 요구 사항 1: 실시간 메시지 연동 로직 (카카오톡 ![][image1] 슬랙)**

본 시스템의 가장 핵심적인 기능은 고객이 카카오톡 채널로 발송한 메시지를 지정된 슬랙 채널로 지연 없이 릴레이하고, 상담원이 슬랙에서 작성한 답변을 다시 해당 고객의 카카오톡 대화창으로 릴레이하는 양방향 실시간 동기화 매커니즘이다. 이를 위해 양 플랫폼이 제공하는 메시지 페이로드의 구조적 차이를 이해하고 이를 상호 변환하는 정교한 파이프라인이 구축되어야 한다.

### **3.1. 인바운드 파이프라인: 카카오톡 ![][image2] 슬랙 메시지 전송**

고객이 카카오톡 비즈니스 채널을 통해 메시지를 전송하면, 해당 이벤트는 사전에 연동된 상담톡 API 또는 챗봇 스킬 서버를 거쳐 미들웨어 서버의 수신 엔드포인트로 인입된다.13 인포뱅크 상담톡 API 등의 벤더를 활용할 경우, 미들웨어는 POST /cstalk/seen\_info 또는 메시지 수신 엔드포인트를 통해 JSON 포맷의 웹훅 데이터를 전달받게 된다.11

수신된 페이로드에는 해당 메시지를 발송한 고객을 고유하게 식별할 수 있는 식별자가 포함된다. 상담톡 연동 구조에 따라 카카오 로그인을 통한 app\_user\_id가 제공되거나, 채널 친구 추가만으로 생성되는 임시 식별자인 userKey (또는 user\_key)가 포함된다.11 이 식별자는 고객과 1:1로 매핑된 슬랙 채널을 식별하는 기본 키(Primary Key) 역할을 수행한다.

미들웨어는 추출된 userKey를 바탕으로 내부 관계형 데이터베이스를 조회하여 해당 고객과 매핑된 슬랙 채널의 고유 ID(channel\_id)를 획득한다. 슬랙으로의 메시지 발송은 슬랙 Web API의 chat.postMessage 메서드를 호출하여 이루어진다.16 이때 슬랙 API로 전달되는 JSON 페이로드는 단순한 텍스트 구조를 넘어, 상담원이 메시지의 출처와 고객 정보를 직관적으로 파악할 수 있도록 슬랙의 Attachments 또는 Block Kit 레이아웃을 활용하여 풍부하게 구성되어야 한다.17

| 슬랙 chat.postMessage 주요 구성 속성 | 적용 내용 및 목적 |
| :---- | :---- |
| channel | DB에서 조회된 고객 전용 1:1 슬랙 채널 ID |
| text | 카카오톡에서 추출된 고객의 실제 발화 텍스트 본문 |
| username | 슬랙 메시지의 발신자 이름을 고객의 카카오톡 닉네임 또는 임시 ID로 동적 변경 |
| icon\_url | 발신자의 프로필 이미지를 동적으로 적용하여 상담원의 시각적 인지 능력 향상 |
| metadata | 메시지 메타데이터 설계 지침에 따라 카카오톡 타임스탬프(kakaoTime), 이벤트 ID(sessionId) 등 원본 데이터를 은닉하여 향후 감사 및 추적에 활용 11 |

### **3.2. 아웃바운드 파이프라인: 슬랙 ![][image2] 카카오톡 메시지 전송**

상담원이 고객과 매핑된 슬랙 채널에서 답변을 입력하면, 슬랙의 Events API가 미들웨어 서버에 message 이벤트를 비동기적으로 발송한다. 슬랙의 아웃바운드 통신은 레거시 형태인 Outgoing Webhooks 대신, 체계적인 이벤트 구독 모델과 보안성을 제공하는 Events API 기반의 앱 구조를 채택해야 한다.20 이를 위해 슬랙 대시보드의 'Event Subscriptions' 메뉴에서 message.channels, message.groups 등의 이벤트를 구독 설정해야 한다.21

슬랙 서버로부터 도달하는 이벤트 페이로드는 event\_callback 타입으로 래핑되어 있으며, 그 내부의 event 객체에 실질적인 메시지 데이터가 담겨 있다.21

| 슬랙 Events API message 객체 핵심 속성 | 설명 및 처리 로직 |
| :---- | :---- |
| channel | 메시지가 발생한 슬랙 채널 ID (DB 역참조를 통해 카카오톡 userKey 확보에 사용) 21 |
| user | 메시지를 작성한 상담원의 슬랙 User ID 21 |
| text | 고객에게 발송될 답변 텍스트 21 |
| bot\_id | (존재 시) 해당 메시지가 봇에 의해 생성되었음을 의미. 무한 루프 방지를 위해 필터링 필요 21 |

미들웨어는 이벤트 페이로드에 bot\_id 속성이 존재하거나 display\_as\_bot이 true인 경우, 이를 미들웨어 자신이 고객의 메시지를 릴레이한 것으로 간주하여 즉시 처리를 중단하고 응답을 반환함으로써 메시지 무한 발송 루프(Infinite Loop)를 방어해야 한다.21 유효한 상담원의 발화로 판명된 경우, channel ID를 기준으로 데이터베이스를 역참조하여 카카오톡 고객 식별자를 찾아낸다. 이후 확보된 식별자와 텍스트 본문을 바탕으로 카카오 비즈메시지 API 또는 챗봇 스킬 응답 규격에 맞는 JSON 포맷을 구성하여 카카오 서버로 발송하며 22, 최종적으로 고객의 카카오톡 채팅방에 상담원의 메시지가 렌더링된다.

## **4\. 상세 기능 요구 사항 2: 1:1 채팅방 및 슬랙 채널 자동 생성 및 매핑**

수많은 고객의 문의를 하나의 공통 채널에서 처리할 경우, 대화의 맥락이 뒤섞여 상담 품질이 급격히 저하되고 메시지 오발송 사고가 발생할 위험이 높다. 따라서 본 시스템은 새로운 고객이 카카오톡 채널에 접근하여 최초로 메시지를 발송하는 즉시, 슬랙 워크스페이스 내에 해당 고객만을 전담하기 위한 독립적인 1:1 채널을 자동으로 생성하고 데이터베이스를 통해 영속적으로 매핑하는 자동화 파이프라인을 구축해야 한다.24

### **4.1. 슬랙 채널 자동 생성 로직 및 엄격한 명명 규칙(Naming Convention)**

미들웨어는 카카오톡으로부터 이벤트를 수신할 때마다 추출된 userKey가 내부 데이터베이스의 매핑 테이블에 존재하는지 확인한다. 매핑 정보가 존재하지 않는 신규 고객일 경우, 미들웨어의 Celery 워커는 즉시 슬랙 Web API의 conversations.create 메서드를 호출하여 새로운 프라이빗 또는 퍼블릭 채널 생성을 시도한다.25

이 과정에서 슬랙 API가 강제하는 엄격한 채널 명명 규칙을 반드시 준수해야 시스템 오류를 방지할 수 있다. 슬랙의 채널 이름은 최대 80자를 초과할 수 없으며, 오직 영문 소문자, 숫자, 하이픈(-), 밑줄(\_)만을 허용한다.25 카카오톡 고객의 닉네임은 한글, 이모지, 특수문자, 띄어쓰기 등이 혼재될 수 있으므로 이를 그대로 슬랙 채널명으로 사용할 수 없다. 따라서 미들웨어는 정규표현식(^\[a-z0-9-\_\]{1,80}$) 검증을 통과할 수 있도록 고객 식별자를 해시 처리하거나, 특정 접두사를 결합하여 고유하고 안전한 채널명(예: cs-user-kakao-a1b2c3d4)을 동적으로 생성하는 네이밍 파이프라인을 갖추어야 한다.25

채널 생성이 성공적으로 완료되면, 슬랙 API 응답 페이로드에 포함된 고유한 채널 식별자 ID (예: C0EAQDV4Z)를 추출하여 내부 관계형 데이터베이스에 카카오톡 userKey와 1:1 매핑 관계로 영구 저장한다.25

### **4.2. API Rate Limit 초과 대응: 트리아지(Triage) 채널과 비동기 백오프 패턴**

채널 생성 API인 conversations.create는 슬랙의 Rate Limit 정책 상 Tier 2에 속하며, 허용량이 분당 20회(20+ per minute)로 상당히 제한적이다.25 마케팅 메시지(알림톡/친구톡) 발송 직후 등 카카오톡 채널을 통해 수십에서 수백 명의 고객이 동시에 최초 메시지를 발송하는 피크 트래픽(Peak Traffic) 상황에서는, 분당 20회 제한이 즉각적인 병목으로 작용하여 슬랙 API가 TooManyRequests (HTTP 429\) 에러를 반환하게 된다.28

단순 순차적 API 호출 구조에서 이러한 한도 초과 오류가 발생할 경우, 미들웨어 전체의 스레드가 블로킹되거나 애플리케이션 자체가 다운되는 연쇄 장애가 발생할 수 있다.28 이를 방지하고 데이터 유실을 막기 위해 두 가지 건축적 대응 방안이 시스템 코어에 구현되어야 한다.

첫째, 지수 백오프(Exponential Backoff)를 적용한 재시도 큐 운용이다. 슬랙 API 응답의 Retry-After 헤더 값을 분석하여, 해당 시간만큼 대기한 후 비동기적으로 채널 생성을 재시도하는 로직을 Celery 워커에 적용해야 한다.28

둘째, 임시 공통 채널인 '트리아지(Triage) 채널' 패턴의 도입이다. 고객 전용 1:1 채널 생성이 Rate Limit에 의해 지연 대기 상태에 빠질 경우, 고객이 발송한 최초 메시지가 유실되지 않도록 사전에 지정된 공용 슬랙 채널(예: \#cs-inbound-triage)로 메시지를 우선 라우팅하여 상담원이 즉시 대응할 수 있도록 조치한다. 이후 1:1 채널 생성이 완료되면, 백그라운드 태스크가 공용 채널에 생성된 메시지 스레드의 링크나 컨텍스트를 신규 채널로 동기화하여 업무의 영속성을 보장한다.

## **5\. 상세 기능 요구 사항 3: 양방향 미디어 파일 전송 파이프라인**

텍스트 메시지 전송을 넘어서는 풍부한 고객 지원을 제공하기 위해 이미지, 문서, 동영상 등 다양한 형태의 첨부 파일을 카카오톡과 슬랙 양방향으로 원활하게 전송할 수 있는 견고한 데이터 파이프라인 구축이 필수적이다. 카카오톡과 슬랙은 허용하는 미디어 파일의 규격, 용량 제한, 그리고 전송 프로토콜 방식에 있어 상당한 기술적 차이를 보이므로, 미들웨어는 단순한 릴레이를 넘어 데이터를 적극적으로 변환하고 조율하는 역할을 수행해야 한다.

### **5.1. 인바운드 파일 전송: 카카오톡 ![][image2] 슬랙 업로드 아키텍처**

고객이 카카오톡 채팅창을 통해 이미지나 문서를 전송하면, 미들웨어는 카카오 웹훅을 통해 해당 미디어 파일에 접근할 수 있는 외부 다운로드 URL과 메타데이터 정보를 수신한다.29 미들웨어는 이 URL에서 파일 바이너리 스트림을 임시 메모리나 스토리지에 다운로드한 후, 슬랙 API를 통해 상담원 채널로 업로드하는 절차를 거친다.

최근 슬랙 API의 파일 업로드 방식은 기존의 단일 POST 요청에서 3단계로 구성된 비동기 워크플로우로 전면 개편되었다.30

1. **업로드 URL 획득**: 미들웨어는 파일의 이름(filename)과 바이트 단위의 정확한 크기(length) 정보를 포함하여 files.getUploadURLExternal API를 우선 호출해야 한다.30 슬랙 서버는 이에 대한 응답으로 파일 데이터를 전송할 수 있는 외부 upload\_url과 고유 식별자인 file\_id를 반환한다.30  
2. **바이너리 데이터 POST**: 획득한 upload\_url을 향해 미들웨어는 다운로드 해둔 파일의 실제 바이너리 데이터를 POST 방식으로 전송한다.30  
3. **메시지 결합**: 파일 업로드 비동기 작업이 성공하여 HTTP 200 응답을 수신하면, 최종적으로 해당 file\_id를 활용하여 대상 슬랙 채널에 chat.postMessage API로 메시지와 파일을 결합하여 게시한다.30

슬랙의 플랫폼 파일 업로드 한도는 파일당 최대 1GB로 매우 넉넉한 편이므로 33, 카카오톡에서 발송된 대부분의 고객 파일은 미들웨어의 크기 변환 없이 안전하게 슬랙으로 전송될 수 있다.

### **5.2. 아웃바운드 파일 전송: 슬랙 ![][image2] 카카오톡 및 규격 최적화 파이프라인**

반대로 상담원이 슬랙 환경에서 파일 업로드 기능을 이용해 이미지를 전송할 경우, 슬랙 Events API는 message 이벤트의 하위 배열로 files 객체를 포함하여 페이로드를 전달한다.21

#### **슬랙 파일 메타데이터 구조 및 다운로드 로직**

전달된 files 객체 내에는 파일의 고유 식별자(id), 이름(name), 마임타입(mimetype), 크기(size), 그리고 썸네일 정보와 함께 파일 원본을 다운로드할 수 있는 접근 URL인 url\_private 및 url\_private\_download 등의 상세한 메타데이터가 포함되어 있다.21 미들웨어는 이 url\_private\_download 주소를 이용해 슬랙 서버로부터 파일 원본을 다운로드해야 하며, 슬랙의 보안 정책상 이 URL에 접근하기 위해서는 반드시 HTTP 요청 헤더에 Authorization: Bearer {Bot Token} 형식의 인증 정보를 포함해야 정상적으로 다운로드가 가능하다.21

#### **카카오 비즈메시지 제약 사항 및 동적 이미지 리사이징(Resizing)**

슬랙에서 성공적으로 다운로드된 파일은 카카오 서버로 전달되기 전, 카카오 비즈메시지 및 챗봇 API가 요구하는 극도로 엄격한 규격 제약 조건에 맞게 검증 및 변환 과정을 거쳐야만 한다. 슬랙과 달리 카카오는 모바일 네트워크 환경의 최적화를 위해 미디어 파일의 용량을 강하게 통제한다. 일반적인 카카오 알림톡이나 친구톡 이미지의 경우 최대 허용 용량이 500KB 이하로 제한되거나, 해상도 비율(예: 800x600 픽셀 기준)에 따라 최대 2MB까지만 업로드가 허용되는 등의 제약이 상존한다.35 만약 RFC2396, RFC1034 등의 웹 표준을 준수하지 않는 URL 포맷이나 제한을 초과하는 용량의 파일을 발송할 경우, 카카오 서버는 해당 이미지를 클라이언트에 표시하지 않거나 전송 자체를 거부한다.36

따라서 미들웨어 내에는 Python의 Pillow나 OpenCV와 같은 고성능 이미지 처리 라이브러리를 활용한 동적 리사이징(Resizing) 및 압축(Compression) 모듈이 반드시 파이프라인 내에 포함되어야 한다. 슬랙에서 다운로드한 이미지의 크기가 카카오의 허용 한계(예: 500KB)를 초과하는 경우, 시스템은 품질(Quality) 속성을 점진적으로 낮추거나 이미지의 물리적 해상도를 비율에 맞게 축소하여 규격 이내로 최적화한 후 카카오 서버로 전송해야 한다.

만약 압축을 통해서도 해결할 수 없는 대용량 동영상이나 PDF 등의 문서 파일의 경우, 미들웨어는 파일을 즉시 AWS S3와 같은 자체 클라우드 객체 스토리지(Object Storage)에 업로드하고, 생성된 공개 다운로드 URL 링크를 추출하여 이를 텍스트 메시지 포맷으로 변환하여 고객에게 전송하는 우회(Fallback) 전략을 기본 동작으로 채택해야 한다.38 이를 통해 플랫폼 간의 물리적 용량 한계를 극복하고 사용자의 원활한 파일 교환 경험을 보장한다.

## **6\. 플랫폼별 API 연동 정책, 보안 아키텍처 및 Rate Limit 대응 설계**

두 플랫폼 간의 신뢰성 있는 양방향 데이터 교환을 보장하기 위해 카카오톡과 슬랙 양측이 고수하는 플랫폼별 인증 체계, 암호화 기반 보안 정책, 그리고 서버 자원 보호를 위한 Rate Limit 정책을 시스템 코어 로직에 깊숙이 반영해야 한다.

### **6.1. 카카오톡 API 보안 및 웹훅 정책 요구사항**

#### **초저지연 타임아웃(Timeout) 규정 준수**

카카오 개발자 문서와 API 가이드라인에 명시된 가장 크리티컬한 운영 정책은 미들웨어가 카카오 서버로부터 수신하는 모든 웹훅 요청에 대해 3초 이내에 올바른 HTTP 상태 코드(예: 200 OK, 202 Accepted)로 응답해야 한다는 것이다.4 앞서 아키텍처 설계에서 논의한 바와 같이 이를 준수하지 못할 경우, 카카오 시스템은 전송 실패로 간주하고 최대 3회에 걸쳐 재전송을 시도하며 11, 타임아웃 에러율이 지속적으로 높게 관찰될 경우 궁극적으로 기업 계정의 웹훅 호출 권한을 장기적으로 비활성화(Deactivation) 조치할 수 있다. 비동기 메시지 브로커(Celery/Redis) 기반의 설계는 이 3초 제약 조건을 회피하기 위한 가장 확실한 기술적 대응이다.

#### **무결성 검증을 위한 서명(Signature) 및 헤더 유효성 확인**

공용 인터넷 망에 노출된 미들웨어 웹훅 엔드포인트는 악의적인 제3자의 데이터 위조(Spoofing) 공격이나 무작위 페이로드 삽입 공격에 취약하다. 이를 방어하기 위해 미들웨어는 인입되는 웹훅 요청의 진위 여부를 암호학적으로 검증해야 한다. 카카오 웹훅은 HTTP 헤더에 앱 인증을 위한 키와 서명을 포함하여 전송된다.

* **기본 관리자 키 검증**: 요청 헤더에 포함된 Authorization: KakaoAK ${SERVICE\_APP\_ADMIN\_KEY} 값을 파싱하여, 카카오 디벨로퍼스 콘솔에서 사전에 발급받은 '기본 관리자 키(Primary admin key)'와 일치하는지 대조하는 미들웨어 레이어(Middleware Layer)를 구축해야 한다.4 값이 불일치할 경우 즉시 HTTP 401 Unauthorized를 반환하고 연결을 차단한다.  
* **리소스 중복 방지**: 헤더 내의 X-Kakao-Resource-ID 필드를 확인하여 이벤트의 고유성을 식별하고, Redis의 만료 시간(TTL) 기반 캐싱을 이용해 동일한 ID로 수신된 중복 웹훅을 필터링하는 방어 로직을 적용해야 한다.4  
* **서명 검증**: 강화된 보안이 필요한 경우 RFC7515 규격을 따르는 JSON Web Token(JWT) 기반의 페이로드 서명(Signature) 검증 과정을 구현하여, 통신 과정에서 데이터가 위변조되지 않았음을 수학적으로 확정지어야 한다.39

#### **방화벽(Firewall) 및 IP 허용 목록(Allowlist) 정책 구성**

엔터프라이즈 서버 환경이나 AWS 클라우드 내부에서 접근 제어 목록(ACL) 및 보안 그룹(Security Group)을 운용할 경우, 카카오 서버의 웹훅 발송 IP 대역을 인바운드 룰(Inbound Rule)에 명시적으로 허용해야만 트래픽이 차단되지 않는다.4 카카오 채널 및 상담톡 연동 문서에 명시된 주요 IP 대역(211.115.98.154, 211.115.98.155, 211.115.98.205, 3.37.214.83, 3.39.75.204, 43.200.251.230 등)과 서브넷 정보(121.53.90.32/27, 211.242.11.0/27 등)를 모두 인프라 설정 스크립트(Terraform 등)에 반영해야 한다.4 동시에 카카오 서버의 물리적 IP 대역은 인프라 증설에 따라 변동될 가능성이 있으므로 호스트 네임(도메인) 기반의 웹 방화벽(WAF) 구성을 병행하는 것이 강력히 권장된다.4

### **6.2. 슬랙 API 보안 및 Rate Limit 변경에 따른 필수 아키텍처 대응**

슬랙 페이로드를 수신하기 위해서는 단순한 외부 웹훅(Incoming Webhooks)이 아닌, 양방향 통신과 권한 제어가 용이한 Events API 구조를 활용하여 인증된 앱 기반으로 접근해야 한다.20

#### **슬랙 엔드포인트 소유권 인증(Challenge Verification)**

미들웨어가 슬랙의 이벤트 구독 엔드포인트로 작동하기 위해서는 초기 설정 단계에서 url\_verification 이벤트를 처리할 수 있는 로직을 구비해야 한다.10 슬랙 서버가 발송한 challenge 문자열 파라미터를 그대로 추출하여 HTTP 200 OK 응답 본문으로 반환해야만 엔드포인트의 소유권이 증명되어 이후의 실제 메시지 이벤트를 수신할 수 있다.

#### **결정적인 아키텍처 요구사항: 슬랙 'Internal App' 등록**

슬랙 API 연동 아키텍처를 설계함에 있어 전체 프로젝트의 성패를 좌우하는 가장 치명적인 요소는 최근 변경된 슬랙의 API 호출 제한(Rate Limit) 정책에 대한 대응이다. 슬랙은 시스템 전역의 안정성을 유지하고 무분별한 데이터 엑스필트레이션(Exfiltration)을 방지하기 위해 각 API 엔드포인트마다 엄격한 티어(Tier) 기반의 호출 제한을 두고 있다.27

특히 주목해야 할 점은 2025년 5월 29일 자로 전격 적용된 비-마켓플레이스(Non-Marketplace) 상용 배포 앱에 대한 극단적인 스로틀링(Throttling) 규제이다.42 변경된 정책에 따르면, 디렉토리에 정식 등록되지 않은 일반적인 외부 연동 앱이 채널의 과거 메시지를 조회하거나 스레드의 컨텍스트를 파악하기 위해 주로 사용하는 conversations.history 및 conversations.replies API 메서드는 분당 단 1회 호출, 호출당 최대 15개 메시지 반환이라는 극도로 보수적인 제약을 적용받게 된다.42 이러한 API 한도 초과는 별도의 에러 메시지 없이 침묵의 실패(Silent failure)를 야기하여, 상담 시스템의 메시지 동기화 누락이라는 치명적인 장애를 유발한다.44

수많은 고객이 실시간으로 발송하는 메시지를 지연 없이 수집하고 양방향 동기화를 유지해야 하는 본 시스템의 특성상, 이처럼 강력한 호출 제한을 우회하여 정상적인 서비스 품질(QoS)을 유지하기 위한 유일한 건축적 해결책은 명확하다. 본 통합 커뮤니케이션 시스템의 슬랙 앱 인증을 외부 상용 배포용이 아닌, 특정 기업 워크스페이스 내에서만 배타적으로 운영되는 \*\*'내부 고객 자체 구축 애플리케이션(Internal customer-built application)'\*\*으로 정의하고 디렉토리에 승인 등록하는 절차를 반드시 밟아야 한다.42 슬랙의 내부 앱으로 인증받을 경우 규제 대상에서 면제되어 기존과 동일하게 티어 3 수준에 해당하는 분당 50회 이상의 호출 한도와 요청당 1,000개의 객체 반환 한도를 유지할 수 있으므로 42, 대규모 동시 다발적인 고객 상담 트래픽을 API 차단 없이 지연 없이 소화할 수 있는 인프라적 안정성을 확보할 수 있다.

## **7\. 데이터베이스 스키마 및 상태 동기화 매커니즘**

미들웨어의 관계형 데이터베이스(RDBMS)는 단순히 데이터를 저장하는 공간을 넘어, 양쪽 플랫폼 간의 비동기적 통신 상태를 추적하고 사용자 식별자를 영속적으로 맵핑하는 핵심 상태 저장소(State Store)로 기능한다. 복잡한 트랜잭션 무결성 보장과 뛰어난 읽기/쓰기 성능을 제공하는 PostgreSQL 또는 Amazon Aurora 환경의 도입을 표준으로 한다.3

### **7.1. 데이터 모델링 핵심 요구사항**

| 스키마 테이블명 | 역할 정의 및 핵심 컬럼 상세 구조 |
| :---- | :---- |
| **Channel\_Mapping** | 카카오 고객과 슬랙 채널 간의 1:1 관계를 관리하는 중앙 레지스트리. • kakao\_user\_key (VARCHAR, PK): 카카오 측의 고유 사용자 식별자. 외래키 참조의 기준점 15 • slack\_channel\_id (VARCHAR, UNIQUE): 슬랙 conversations.create에서 반환한 C로 시작하는 채널 고유 식별 ID 25 • channel\_name (VARCHAR): 매핑된 슬랙 채널 명명 규칙에 따라 생성된 채널 문자열 • created\_at (TIMESTAMP), status (ENUM: 'ACTIVE', 'ARCHIVED') |
| **Message\_Log** | 이벤트 누락 확인 및 사후 감사를 위해 송수신된 모든 메시지 트랜잭션 이력을 보존. • message\_id (UUID, PK): 미들웨어 통합 관리 고유 트랜잭션 식별 ID • kakao\_message\_id (VARCHAR): 카카오 측 이벤트 송수신 식별자 • slack\_ts (VARCHAR): 슬랙의 고유 타임스탬프 기반 메시지 ID. 스레드 동기화에 필수 21 • direction (ENUM): 데이터 흐름 방향 (KAKAO\_TO\_SLACK 또는 SLACK\_TO\_KAKAO) • payload\_type (ENUM): 전송 데이터의 형식 (텍스트, 이미지, 파일, 문서 등) |
| **User\_Session** | 고객의 상담톡 진입 여부, 마지막 발화 시간 등을 기록하여 세션 만료 및 휴면 상태를 분류. • kakao\_user\_key (VARCHAR, PK) • last\_active\_at (TIMESTAMP): 최후 활성 시간 • is\_blocked (BOOLEAN): 채널 차단 여부 추적 상태 플래그 |

### **7.2. 카카오톡 언링크(Unlink) 및 차단 이벤트 처리 기반의 라이프사이클 관리**

채널 맵핑 로직의 무결성과 데이터베이스의 최신성을 유지하기 위해, 새로운 카카오 이벤트가 유입될 때마다 Channel\_Mapping 테이블을 빠르게 조회하여 세션의 유효성을 검사하는 인메모리 캐시(Redis) 레이어가 가동되어야 한다.

특히 유의해야 할 정책적 비즈니스 시나리오는 고객이 상담 종료 후 카카오톡 채널을 직접 차단(Block)하거나, 카카오 계정 연동을 해제(Unlink)하는 경우이다. 이 경우 카카오 서버는 즉각적으로 미들웨어의 지정된 엔드포인트로 Kakao Talk Channel webhook (이벤트 속성: "blocked") 또는 Unlink webhook 이벤트를 발송하게 된다.4

미들웨어 백엔드는 해당 웹훅을 수신하는 즉시 관계형 데이터베이스 User\_Session 테이블의 상태를 is\_blocked \= true로 갱신해야 한다. 이와 동시에, 비즈니스 룰에 따라 백그라운드 태스크가 트리거되어 해당 고객과 연결되어 있던 슬랙 1:1 채널에 자동화된 봇 메시지("고객이 채널을 차단하여 더 이상 메시지를 발송할 수 없습니다")를 알림으로 전송하고, 불필요한 슬랙 워크스페이스 리소스 점유를 해소하기 위해 해당 채널을 자동 아카이브(Archive) 처리하거나 상태를 비활성화하는 등 고객의 행동에 대응하는 완벽한 채널 라이프사이클 관리(Lifecycle Management) 기능이 데이터베이스 동기화 로직에 포함되어야 한다.4

## **8\. 예외 처리, 모니터링 및 장애 복구(Resilience) 전략**

이질적인 두 거대 플랫폼의 API 생태계를 네트워크를 통해 실시간으로 연동하는 분산 아키텍처 환경에서는 네트워크 패킷 손실, 인프라의 일시적 마비, 혹은 서드파티 서비스(카카오, 슬랙)의 일시적 장애가 빈번하게 발생한다. 이러한 예측 불가능한 장애 요인으로부터 고객의 소중한 소통 기록을 안전하게 보존하고, 시스템의 회복 탄력성(Resilience)을 영구적으로 확보하기 위해 포괄적이고 자동화된 장애 복구 전략이 구축되어야 한다.46

### **8.1. 비동기 재시도(Retry) 알고리즘 및 지수 백오프의 정교화**

미들웨어에서 외부로 나가는 발신 웹훅(Outbound Webhooks) 처리 과정, 예를 들어 카카오 서버로 메시지를 쏘거나 슬랙 API를 호출하는 과정에서 5xx 계열의 서버 측 내부 오류(500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable, 504 Gateway Timeout)나 연결 시간 초과(Connection timeout)가 발생할 경우, 미들웨어는 해당 이벤트를 즉각적으로 메모리에서 폐기해서는 안 된다.46 이는 일시적인 네트워크 히컵(Hiccup) 현상일 가능성이 높기 때문이다.

대신 실패한 이벤트를 Celery의 재시도 큐(Retry Queue)로 즉시 이관하고, 지수 백오프(Exponential Backoff) 알고리즘에 따라 대기 시간을 점진적으로 늘려가며(예: 2초, 4초, 8초, 16초) 재전송을 시도하는 탄력적 로직을 구현해야 한다. 반면, 영구적인 시스템적 오류인 4xx 인증 실패(401 Unauthorized), 존재하지 않는 채널 전송 시도(404 Not Found), 혹은 페이로드 규격 오류(400 Bad Request) 등에 대해서는 재시도를 거듭해도 성공할 수 없으므로, 재시도 없이 처리를 즉각 중단하고 치명적 에러 로깅을 수행하여 무의미한 컴퓨팅 자원 낭비와 추가적인 API Rate Limit 소진을 방지해야 한다.46

### **8.2. 데드 레터 큐(DLQ, Dead Letter Queue) 운용 체계**

시스템에서 설정한 최대 재시도 횟수(예: 5회)를 초과하여 최종적으로 처리에 실패한 비운의 메시지들은 소실을 방지하기 위해 별도의 보관소인 데드 레터 큐(DLQ)에 안전하게 적재되어야 한다.3 DLQ에 보관된 메시지들은 관리자나 개발 엔지니어가 직접 원본 페이로드를 확인하고 실패 원인을 상세 분석할 수 있도록 해야 하며, 원인 파악 및 외부 시스템의 장애가 복구된 이후 수동으로 해당 메시지를 다시 큐에 밀어 넣어 재처리(Replay)할 수 있도록 슬랙 내부 커맨드 인터페이스나 전용 어드민 대시보드를 함께 제공하는 것이 장애 대처의 모범 사례이다.3

### **8.3. 전 구간 모니터링 및 로깅 추적(Traceability) 체계 구축**

양방향 데이터 흐름의 투명성을 확보하기 위해 FastAPI 미들웨어 전역에 강력하고 구조화된 로깅 체계를 구축해야 한다. 파이썬 생태계의 Loguru와 같은 직관적인 비동기 로깅 라이브러리를 통해 표준화된 JSON 포맷의 구조화 로그를 생성하고 47, Datadog이나 AWS CloudWatch, ELK(Elasticsearch, Logstash, Kibana) 스택과 연동하여 시각적 모니터링을 구현해야 한다.

특히 카카오톡 웹훅의 헤더에 포함되어 전달되는 X-Kakao-Resource-ID와 같이 고유한 이벤트 트래킹 ID를 수신 단계부터 발췌하여 미들웨어 내부의 모든 로그 메타데이터에 일관되게 주입(Injection)해야 한다.4 이를 통해 카카오톡에서 시작된 단일 고객 메시지가 미들웨어를 거쳐 슬랙 채널의 특정 타임스탬프(slack\_ts)에 도달하기까지의 전체 릴레이 라이프사이클을 고유 ID 하나로 끊김 없이 추적(Distributed Traceability)할 수 있는 완벽한 감사(Audit) 추적성을 보장해야만 운영 중 발생하는 병목 구간을 신속하게 진단하고 최적화할 수 있다.

이러한 고도의 아키텍처, 촘촘한 에러 핸들링, 그리고 각 플랫폼의 API 정책을 정밀하게 준수하는 설계를 바탕으로 개발된 백엔드 미들웨어 시스템은 기업 내부의 업무 생산성을 혁신적으로 극대화하며, 동시에 외부 고객에게 지연 없는 무결점의 커뮤니케이션 경험을 선사하는 지능형 통합 인프라로 기능할 것이다.

#### **참고 자료**

1. Best Practices in FastAPI Architecture: A Complete Guide to Building Scalable, Modern APIs, 4월 13, 2026에 액세스, [https://zyneto.com/blog/best-practices-in-fastapi-architecture](https://zyneto.com/blog/best-practices-in-fastapi-architecture)  
2. The simplest way to make FastAPI Slack work like it should \- Hoop.dev, 4월 13, 2026에 액세스, [https://hoop.dev/blog/the-simplest-way-to-make-fastapi-slack-work-like-it-should/](https://hoop.dev/blog/the-simplest-way-to-make-fastapi-slack-work-like-it-should/)  
3. Building a Real-Time Notification Service with FastAPI, Redis Streams, and WebSockets, 4월 13, 2026에 액세스, [https://dev.to/geetnsh2k1/building-a-real-time-notification-service-with-fastapi-redis-streams-and-websockets-52ib](https://dev.to/geetnsh2k1/building-a-real-time-notification-service-with-fastapi-redis-streams-and-websockets-52ib)  
4. Webhook | Kakao Developers Docs, 4월 13, 2026에 액세스, [https://developers.kakao.com/docs/latest/en/getting-started/callback](https://developers.kakao.com/docs/latest/en/getting-started/callback)  
5. FastAPI \+ OCR Pipeline \- BackgroundTasks vs Celery/Redis? \- Reddit, 4월 13, 2026에 액세스, [https://www.reddit.com/r/FastAPI/comments/1s3tzix/fastapi\_ocr\_pipeline\_backgroundtasks\_vs/](https://www.reddit.com/r/FastAPI/comments/1s3tzix/fastapi_ocr_pipeline_backgroundtasks_vs/)  
6. The Definitive Guide to Celery and FastAPI \- Introduction \- TestDriven.io, 4월 13, 2026에 액세스, [https://testdriven.io/courses/fastapi-celery/intro/](https://testdriven.io/courses/fastapi-celery/intro/)  
7. What's the difference between FastAPI background tasks and Celery tasks? \- Stack Overflow, 4월 13, 2026에 액세스, [https://stackoverflow.com/questions/74508774/whats-the-difference-between-fastapi-background-tasks-and-celery-tasks](https://stackoverflow.com/questions/74508774/whats-the-difference-between-fastapi-background-tasks-and-celery-tasks)  
8. should I use AWS Lambda or a web framework like FASTAPI for my background job? : r/Python \- Reddit, 4월 13, 2026에 액세스, [https://www.reddit.com/r/Python/comments/1ovxuif/should\_i\_use\_aws\_lambda\_or\_a\_web\_framework\_like/](https://www.reddit.com/r/Python/comments/1ovxuif/should_i_use_aws_lambda_or_a_web_framework_like/)  
9. Deploying FastAPI to AWS: Part 3 \- Going Serverless with Lambda \- DEV Community, 4월 13, 2026에 액세스, [https://dev.to/ntanwir10/deploying-fastapi-to-aws-part-3-going-serverless-with-lambda-2aj8](https://dev.to/ntanwir10/deploying-fastapi-to-aws-part-3-going-serverless-with-lambda-2aj8)  
10. How to Troubleshoot Webhooks and Resolve Issues in ChatBot, 4월 13, 2026에 액세스, [https://www.chatbot.com/help/webhooks/webhooks-troubleshooting/](https://www.chatbot.com/help/webhooks/webhooks-troubleshooting/)  
11. 사용자 읽음 정보 수신 | 비즈고 API 개발가이드 \- GitBook, 4월 13, 2026에 액세스, [https://infobank-guide.gitbook.io/omni-api-v2/comm/kakao/cstalk/chat-recv/user-read](https://infobank-guide.gitbook.io/omni-api-v2/comm/kakao/cstalk/chat-recv/user-read)  
12. A FinOps Guide to Comparing Containers and Serverless Functions for Compute \- AWS, 4월 13, 2026에 액세스, [https://aws.amazon.com/blogs/aws-cloud-financial-management/a-finops-guide-to-comparing-containers-and-serverless-functions-for-compute/](https://aws.amazon.com/blogs/aws-cloud-financial-management/a-finops-guide-to-comparing-containers-and-serverless-functions-for-compute/)  
13. 카카오톡 연동하기 \- Channel Talk, 4월 13, 2026에 액세스, [https://docs.channel.io/help/ko/articles/%EC%B9%B4%EC%B9%B4%EC%98%A4%ED%86%A1-%EC%97%B0%EB%8F%99%ED%95%98%EA%B8%B0-04f5721d](https://docs.channel.io/help/ko/articles/%EC%B9%B4%EC%B9%B4%EC%98%A4%ED%86%A1-%EC%97%B0%EB%8F%99%ED%95%98%EA%B8%B0-04f5721d)  
14. 카카오톡 비즈니스 채널을 통한 AI 챗봇 및 채팅 연동, 4월 13, 2026에 액세스, [https://mongmongtory.tistory.com/77](https://mongmongtory.tistory.com/77)  
15. 카카오 비즈니스 상담톡 ( app\_user\_id , user\_key ) \- REST API \- 카카오 데브톡, 4월 13, 2026에 액세스, [https://devtalk.kakao.com/t/app-user-id-user-key/144509](https://devtalk.kakao.com/t/app-user-id-user-key/144509)  
16. Keeping up with the JSONs | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/changelog/2017-10-keeping-up-with-the-jsons](https://docs.slack.dev/changelog/2017-10-keeping-up-with-the-jsons)  
17. Sending messages using incoming webhooks | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks)  
18. slack-api-docs/index\_incoming\_webhooks.md at master \- GitHub, 4월 13, 2026에 액세스, [https://github.com/slackhq/slack-api-docs/blob/master/index\_incoming\_webhooks.md](https://github.com/slackhq/slack-api-docs/blob/master/index_incoming_webhooks.md)  
19. Designing metadata event schema | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/messaging/message-metadata/designing-metadata-event-schema](https://docs.slack.dev/messaging/message-metadata/designing-metadata-event-schema)  
20. The Events API | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/apis/events-api/](https://docs.slack.dev/apis/events-api/)  
21. message event | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/reference/events/message](https://docs.slack.dev/reference/events/message)  
22. chatbot \- KakaoTalk API \- Bot \- Stack Overflow, 4월 13, 2026에 액세스, [https://stackoverflow.com/questions/47282097/kakaotalk-api-bot](https://stackoverflow.com/questions/47282097/kakaotalk-api-bot)  
23. KakaoTalk over API | Infobip Docs, 4월 13, 2026에 액세스, [https://www.infobip.com/docs/kakaotalk/kakaotalk-over-api](https://www.infobip.com/docs/kakaotalk/kakaotalk-over-api)  
24. Slack Connect guide: Work with external organizations, 4월 13, 2026에 액세스, [https://slack.com/help/articles/115004151203-Slack-Connect-guide--Work-with-external-organizations](https://slack.com/help/articles/115004151203-Slack-Connect-guide--Work-with-external-organizations)  
25. conversations.create method | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/reference/methods/conversations.create](https://docs.slack.dev/reference/methods/conversations.create)  
26. Botkit for Slack using regex patterns in conversations \- Stack Overflow, 4월 13, 2026에 액세스, [https://stackoverflow.com/questions/46982916/botkit-for-slack-using-regex-patterns-in-conversations](https://stackoverflow.com/questions/46982916/botkit-for-slack-using-regex-patterns-in-conversations)  
27. Rate limits | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/apis/web-api/rate-limits](https://docs.slack.dev/apis/web-api/rate-limits)  
28. AI Slop: A Slack API Rate Limiting Disaster \- code.dblock.org, 4월 13, 2026에 액세스, [https://code.dblock.org/2026/03/12/ai-slop-a-slack-api-rate-limiting-disaster.html](https://code.dblock.org/2026/03/12/ai-slop-a-slack-api-rate-limiting-disaster.html)  
29. Upload document by the user while talking to the bot \- AI for Service \- Kore.ai Community, 4월 13, 2026에 액세스, [https://community.kore.ai/t/upload-document-by-the-user-while-talking-to-the-bot/4286](https://community.kore.ai/t/upload-document-by-the-user-while-talking-to-the-bot/4286)  
30. files.getUploadURLExternal method | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/reference/methods/files.getUploadURLExternal](https://docs.slack.dev/reference/methods/files.getUploadURLExternal)  
31. files.getUploadURLExternal.json \- slack-api-ref \- GitHub, 4월 13, 2026에 액세스, [https://github.com/slack-ruby/slack-api-ref/blob/master/methods/files/files.getUploadURLExternal.json](https://github.com/slack-ruby/slack-api-ref/blob/master/methods/files/files.getUploadURLExternal.json)  
32. Working with files | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/messaging/working-with-files](https://docs.slack.dev/messaging/working-with-files)  
33. Add files to Slack, 4월 13, 2026에 액세스, [https://slack.com/help/articles/201330736-Add-files-to-Slack](https://slack.com/help/articles/201330736-Add-files-to-Slack)  
34. files.info method | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/reference/methods/files.info](https://docs.slack.dev/reference/methods/files.info)  
35. KakaoTalk | Conversation API \- Sinch Developer Documentation, 4월 13, 2026에 액세스, [https://developers.sinch.com/docs/conversation/channel-support/kakaotalk](https://developers.sinch.com/docs/conversation/channel-support/kakaotalk)  
36. \[카카오톡 공유\] 첨부 이미지 형식 제한 \- General / 일반 FAQ, 4월 13, 2026에 액세스, [https://devtalk.kakao.com/t/topic/2141](https://devtalk.kakao.com/t/topic/2141)  
37. 카카오톡에서 사진 및 동영상 용량 줄여서 전송하기 \- YouTube, 4월 13, 2026에 액세스, [https://www.youtube.com/watch?v=NKgM30TfN6s](https://www.youtube.com/watch?v=NKgM30TfN6s)  
38. \[Make\] API로 나에게 카카오톡 메시지 전송하기, 4월 13, 2026에 액세스, [https://2nd-deck.tistory.com/entry/Make-%EB%82%98%EC%97%90%EA%B2%8C-%EC%B9%B4%EC%B9%B4%EC%98%A4%ED%86%A1-%EB%A9%94%EC%8B%9C%EC%A7%80-%EC%A0%84%EC%86%A1%ED%95%98%EA%B8%B0](https://2nd-deck.tistory.com/entry/Make-%EB%82%98%EC%97%90%EA%B2%8C-%EC%B9%B4%EC%B9%B4%EC%98%A4%ED%86%A1-%EB%A9%94%EC%8B%9C%EC%A7%80-%EC%A0%84%EC%86%A1%ED%95%98%EA%B8%B0)  
39. Webhook | Kakao Developers Docs \- 카카오, 4월 13, 2026에 액세스, [https://developers.kakao.com/docs/latest/en/kakaologin/callback](https://developers.kakao.com/docs/latest/en/kakaologin/callback)  
40. Utilize | Kakao Developers Docs, 4월 13, 2026에 액세스, [https://developers.kakao.com/docs/latest/en/kakaologin/utilize](https://developers.kakao.com/docs/latest/en/kakaologin/utilize)  
41. Guide to Slack Webhooks: Features and Best Practices \- Hookdeck, 4월 13, 2026에 액세스, [https://hookdeck.com/webhooks/platforms/guide-to-slack-webhooks-features-and-best-practices](https://hookdeck.com/webhooks/platforms/guide-to-slack-webhooks-features-and-best-practices)  
42. Rate limit changes for non-Marketplace apps | Slack Developer Docs, 4월 13, 2026에 액세스, [https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps)  
43. Slack conversations.history only returns 15 messages even with limit: 100 \#162325 \- GitHub, 4월 13, 2026에 액세스, [https://github.com/orgs/community/discussions/162325](https://github.com/orgs/community/discussions/162325)  
44. Slack Just Throttled Your OpenClaw Agent. You Probably Haven't Noticed Yet., 4월 13, 2026에 액세스, [https://dev.to/helen\_mireille\_47b02db70c/slack-just-throttled-your-openclaw-agent-you-probably-havent-noticed-yet-d4](https://dev.to/helen_mireille_47b02db70c/slack-just-throttled-your-openclaw-agent-you-probably-havent-noticed-yet-d4)  
45. About Slack's new rate limits... \- APIs You Won't Hate, 4월 13, 2026에 액세스, [https://apisyouwonthate.com/newsletter/about-slacks-new-rate-limits/](https://apisyouwonthate.com/newsletter/about-slacks-new-rate-limits/)  
46. Webhook Retry Best Practices for Sending Webhooks \- Hookdeck, 4월 13, 2026에 액세스, [https://hookdeck.com/outpost/guides/outbound-webhook-retry-best-practices](https://hookdeck.com/outpost/guides/outbound-webhook-retry-best-practices)  
47. Building “PseudoChat”: An AI-Powered Slack Chatbot Using Webhooks, FastAPI, and Together AI | by S2 Data Systems, 4월 13, 2026에 액세스, [https://s2datasystems.medium.com/building-pseudochat-an-ai-powered-slack-chatbot-using-webhooks-fastapi-and-together-ai-43dbfd713ecc](https://s2datasystems.medium.com/building-pseudochat-an-ai-powered-slack-chatbot-using-webhooks-fastapi-and-together-ai-43dbfd713ecc)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAdCAYAAACwuqxLAAAAlUlEQVR4Xu3SsQkCQRCF4RXEPoxsQLCIA2uwCsESLhLtweRiU03swczUAgwuukPfYvaznjOZwnzwkj+ZDTalEP7SWNszwonBo2EoaBmsRtqdsWCmrRkteoYBB23B+MlKe2pz567aORls0vvA0rl8IC9/DJOOYcBOqxi/yS+5MRZMtZrR6shQ8GDwmGhbRrgwhBDCL3sB+REY5YXZudIAAAAASUVORK5CYII=>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAXCAYAAADpwXTaAAAAVUlEQVR4XmNgGAWjgKpgL7oAJeAfugAlwAaIy9AFKQHngNgcXRAETMjEt4B4HwMa8CMTX4NiFgYKwUQg9kYXJAcoAnEnuiC54BO6ACXgMLrAKBhuAACnlhESw2iRqwAAAABJRU5ErkJggg==>