<h2>sungjuk 테이블 목록 보여주기</h2>
<?php
$db_con = mysqli_connect("localhost", "test", "test1234", "testdb");

if (!$db_con) {
    echo "<p>DB 연결 실패</p>";
    exit;
}

$create_sql = "create table if not exists sungjuk (
id int auto_increment primary key,
hakbun varchar(20),
attendance int,
assignment_score int,
midterm_score int,
final_score int,
total_score int,
average_score float,
grade varchar(2),
created_at datetime default current_timestamp
)";
mysqli_query($db_con, $create_sql);

$sql = "select * from sungjuk order by id desc";
$result = mysqli_query($db_con, $sql);

echo "<table border=1 cellpadding=8 cellspacing=0>";
echo "<tr><th>ID</th><th>학번</th><th>출석</th><th>과제</th><th>중간</th><th>기말</th><th>합계</th><th>평균</th><th>평점</th><th>저장일시</th></tr>";

while ($row = mysqli_fetch_assoc($result)) {
    echo "<tr>";
    echo "<td>".$row["id"]."</td>";
    echo "<td>".$row["hakbun"]."</td>";
    echo "<td>".$row["attendance"]."</td>";
    echo "<td>".$row["assignment_score"]."</td>";
    echo "<td>".$row["midterm_score"]."</td>";
    echo "<td>".$row["final_score"]."</td>";
    echo "<td>".$row["total_score"]."</td>";
    echo "<td>".$row["average_score"]."</td>";
    echo "<td>".$row["grade"]."</td>";
    echo "<td>".$row["created_at"]."</td>";
    echo "</tr>";
}

echo "</table>";
mysqli_close($db_con);
?>
<p><a href="sungjuk_proc.php">성적 입력하러 가기</a></p>
