from pprint import pprint

from app.action.media_scrap.yes24_scraper import parse_contents


def test_parse_contents():
    html = (
        "목차<br/><br/>이야기를 열며 <br/>"
        "<br/> 제1강 '카페인 없는 커피' 가게에 오신 것을 "
        "환영합니다 <br/> 이데올로기의 욕망, 또는 욕망의 이데올로기 <br/>"
        "<br/> 제2강 프랜시스 후쿠야마 이후 <br/>"
        "또는 자유민주주의의 종말에 관하여 <br/>\
           <br/> 제3강 새로운 열림의 공간을 향하여 <br/> "
        "다시, '시장근본주의 너머'의 정치를 상상한다는 것"
        "<br/><br/> 제4강 강연이 끝난 후 "
        "<br/> 나와 세계를 바꾸는 '다른 정치'의 조건들 "
        "<br/><br/> 강연자와 옮긴이 소개"
    )

    html = "<b>CHAPTER 03 넷플릭스의 도구들</b>"
    # print(CHARS_TO_DELETE)
    pprint(parse_contents(html))
