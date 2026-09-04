# Git pull / push 매뉴얼

## 작업 시작

```bash
git switch main
git pull --rebase origin main
```

충돌이 나면 파일을 수정한 뒤 `git add <파일>`과 `git rebase --continue`를 실행합니다. 중단하려면 `git rebase --abort`를 사용합니다.

## 작업 후 push

```bash
git status
git diff
git add <변경한 파일>
git commit -m "변경 내용 요약"
git pull --rebase origin main
git push origin main
```

## API 키

- `.env`, `.env.deepseek.face`, `.env.deepseek.saju`는 커밋하지 않습니다.
- 실제 키는 로컬/서버의 키 파일에만 넣고, 저장소에는 `.example` 파일만 올립니다.
- 키 파일이 `git status`에 보이면 `git add`하지 말고 `.gitignore`를 확인합니다.

## 원칙

- 작업 시작 전에 항상 pull/rebase합니다.
- push가 거절되면 강제 push하지 말고 다시 pull/rebase 후 push합니다.
- 충돌 해결 뒤 `git diff --check`를 실행합니다.
