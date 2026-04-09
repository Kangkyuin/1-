<?php
declare(strict_types=1);
require_once __DIR__ . '/db.php';
ensure_sungjuk_table($mysqli);
$r = $mysqli->query('SELECT id,hakbun,attendance,assignment_score,midterm_score,final_score,total_score,average_score,grade,created_at FROM sungjuk ORDER BY id DESC');
if (!$r) exit('목록 조회 실패');
?>
<!doctype html><html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>sungjuk_list.php</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:"Noto Sans KR",sans-serif;background:#f4f7fb;color:#0f172a}
.wrap{max-width:1120px;margin:28px auto;padding:0 14px}.card{background:#fff;border:1px solid #dbe3ee;border-radius:16px;box-shadow:0 12px 28px rgba(2,6,23,.08)}
.top{padding:18px 20px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
a.btn{padding:8px 12px;border-radius:10px;background:#2563eb;color:#fff;text-decoration:none;font-weight:700;font-size:14px}
.tb{padding:14px;overflow:auto}table{width:100%;border-collapse:collapse;min-width:900px}th,td{border-bottom:1px solid #e2e8f0;padding:10px;text-align:center}
th{background:#f8fafc}.grade{font-weight:800;color:#0f766e}.empty{padding:24px;color:#64748b}
</style></head><body><div class="wrap"><div class="card">
<div class="top"><div><h2 style="margin:0">sungjuk 테이블 목록</h2><small>총 <?= (int)$r->num_rows ?>건</small></div><a class="btn" href="sungjuk_proc.php">+ 성적 입력</a></div>
<div class="tb"><table><thead><tr><th>ID</th><th>학번</th><th>출석</th><th>과제</th><th>중간</th><th>기말</th><th>합계</th><th>평균</th><th>평점</th><th>저장일시</th></tr></thead><tbody>
<?php if ($r->num_rows===0): ?><tr><td class="empty" colspan="10">데이터가 없습니다.</td></tr>
<?php else: while($x=$r->fetch_assoc()): ?><tr>
<td><?= (int)$x['id'] ?></td><td><?= htmlspecialchars((string)$x['hakbun'],ENT_QUOTES,'UTF-8') ?></td><td><?= (int)$x['attendance'] ?></td>
<td><?= (int)$x['assignment_score'] ?></td><td><?= (int)$x['midterm_score'] ?></td><td><?= (int)$x['final_score'] ?></td><td><?= (int)$x['total_score'] ?></td>
<td><?= number_format((float)$x['average_score'],2) ?></td><td class="grade"><?= htmlspecialchars((string)$x['grade'],ENT_QUOTES,'UTF-8') ?></td><td><?= htmlspecialchars((string)$x['created_at'],ENT_QUOTES,'UTF-8') ?></td>
</tr><?php endwhile; endif; ?>
</tbody></table></div></div></div></body></html>
