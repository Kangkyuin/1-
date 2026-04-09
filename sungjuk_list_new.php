<h2>SungJuk 테이블 목록 보여주기 (new)</h2>
<hr>
<?php
$db_con = mysqli_connect("localhost", "test", "test1234", "school");
if (!$db_con) {
    exit("<p>DB 연결 실패</p>");
}

$create_sql = "CREATE TABLE IF NOT EXISTS sungjuk (
id INT AUTO_INCREMENT PRIMARY KEY,
student_id VARCHAR(20) NOT NULL,
att INT NOT NULL,
hw INT NOT NULL,
mid INT NOT NULL,
final INT NOT NULL,
total INT NOT NULL,
grade VARCHAR(2) NOT NULL
)";
mysqli_query($db_con, $create_sql);

$sql = "SELECT * FROM sungjuk ORDER BY id DESC";
$result = mysqli_query($db_con, $sql);
if (!$result) {
    exit("<p>조회 실패: " . mysqli_error($db_con) . "</p>");
}

echo "<table border='1' cellpadding='8' cellspacing='0'>
<tr>
<th>ID</th>
<th>학번</th>
<th>출석</th>
<th>과제</th>
<th>중간</th>
<th>기말</th>
<th>합계</th>
<th>평점</th>
</tr>";

while ($row = mysqli_fetch_assoc($result)) {
    echo "<tr>";
    echo "<td>" . $row['id'] . "</td>";
    echo "<td>" . $row['student_id'] . "</td>";
    echo "<td>" . $row['att'] . "</td>";
    echo "<td>" . $row['hw'] . "</td>";
    echo "<td>" . $row['mid'] . "</td>";
    echo "<td>" . $row['final'] . "</td>";
    echo "<td>" . $row['total'] . "</td>";
    echo "<td>" . $row['grade'] . "</td>";
    echo "</tr>";
}
echo "</table>";
mysqli_close($db_con);
?>
<br>
<a href="input.php">성적 입력하러 가기</a>
