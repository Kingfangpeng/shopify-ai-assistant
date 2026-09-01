# Knowledge Base and Chat History

## Implemented Scope

- RAG chat stream emits status events before retrieval and generation.
- Frontend chat stores multiple sessions in `localStorage` and restores the active session after refresh.
- History page lists persisted sessions and can reopen a previous conversation.
- Knowledge page can upload files, rebuild the index, load indexed-file stats, filter chunks by file, view full chunk content, and delete indexed chunks for a file.

## Knowledge API

All endpoints are served under the FastAPI `/api` prefix.

- `GET /api/knowledge/stats`
  - Returns `total_chunks` and per-file chunk counts.
- `GET /api/knowledge/chunks?filename=<name>&limit=50&offset=0`
  - Returns paginated chunks for one file or all files.
  - `file_path` can be used instead of `filename` when the exact stored source path is known.
- `DELETE /api/knowledge/file?file_path=<name-or-source-path>`
  - Deletes chunks matching either the stored source path or uploaded file name.

Legacy frontend paths are still accepted:

- `GET /api/chunks`
- `GET /api/knowledge_stats`

## Verification

Run these from the project root:

```bash
python -m compileall app
```

Run this from `frontend/`:

```bash
npm.cmd run build
```
