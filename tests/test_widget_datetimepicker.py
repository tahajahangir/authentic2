from authentic2.widgets import DateTimeWidget, DateWidget, TimeWidget


def test_widgets_init_and_render_no_locale():
    DateTimeWidget().render('wt', '2019/12/12 12:34:34')
    DateWidget().render('wt', '2019/12/12')
    TimeWidget().render('wt', '12:34:34')


def test_widgets_init_and_render_fr(french_translation):
    DateTimeWidget().render('wt', '2019/12/12 12:34:34')
    DateWidget().render('wt', '2019/12/12')
    TimeWidget().render('wt', '12:34:34')
