## 프로젝트 설명 
1) PySide6 기반의 UI 기반 
2) 특정 폴더나 드라이브 (재귀적 하위검색)에 대한 파일들의 메타데이터를 생성 (메타 데이터는 파일이름, 절대경로, 사이즈)
   - 숨김 파일/폴더는 처리하지 않음
   - 동영상 파일만 대상 (예: mp4, avi, mkv, mov, wmv, webm 등)
3) 2번의 메터 데이터 끼리의 비교를 통해 차이를 메타데이터화 
4) 2번의 생성된 메타데이터는 json형태이나 fcmp_로 시작.
5) DLT Viewer로 내부 상태를 디버깅 할 수 있도록 

## 폴더 구조
1) main 폴더 (UI와 Core를 쓰는 폴더)
2) UI폴더 (UI관련)
3) Core폴더 (엔진/로직)
4) Dist폴더 (배포버전 / Pyinstaller로 실행파일화 )
5) Data폴더 (메타데이터 모음)

## UI 
1) Main UI 
2) MetaData를 생성하기 위한 폴더 선택 버튼 및, nickname설정, 메타 생성 버튼
3) Seperator 
4) 생성된 MetaData는 fcmp_nickname.json 형태이므로 그것들 목록
5) Meta를 두개 선택하면 Compare를 생성하는 UI
6) Compare Meta는 List 뷰로 
7) 하단에는 Status 메타 데이터 실행 시간 표시 / 완료  
8) 메타 생성 중 Status에 현재 처리 중인 폴더와 처리된 파일 개수를 표시  

## Core (Logic) 
1) FCMP_CreateMeta 특정 폴더나 드라이브를 전달하면 메타데이터를 생성하는 클래스
   - 숨김 제외, 동영상 확장자만 수집
2) FCMP_CompareMeta 두개의 메타데이터를 바탕으로 비교하는 로직
3) 메타 생성 진행 콜백으로 (현재 폴더, 처리 파일 수)를 UI/Status에 전달

