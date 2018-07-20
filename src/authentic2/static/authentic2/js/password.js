a2_password_check_equality = (function () {
    return function(id1, id2) {
        $(function () {
            function check_equality() {
                setTimeout(function () {
                    var $help_text = $input2.parent().find('.helptext');
                    var password1 = $input1.val();
                    var password2 = $input2.val();

                    if (! password2) {
                        $help_text.removeClass('a2-password-nok');
                        $help_text.removeClass('a2-password-ok');
                    } else {
                        var equal = (password1 == password2);
                        $help_text.toggleClass('a2-password-ok', equal);
                        $help_text.toggleClass('a2-password-nok', ! equal);
                    }
                }, 0);
            }
            var $input1 = $('#' + id1);
            var $input2 = $('#' + id2);
            $input1.on('change keydown keyup keypress paste', check_equality);
            $input2.on('change keydown keyup keypress paste', check_equality);
        });
    }
})();

a2_password_validate = (function () {
    function toggle_error($elt) {
        $elt.removeClass('a2-password-check-equality-ok');
        $elt.addClass('a2-password-check-equality-error');
    }
    function toggle_ok($elt) {
        $elt.removeClass('a2-password-check-equality-error');
        $elt.addClass('a2-password-check-equality-ok');
    }
    function get_validation($input) {
        var password = $input.val();
        var $help_text = $input.parent().find('.helptext');
        var $policyContainer = $help_text.find('.a2-password-policy-container');
        $.ajax({
            method: 'POST',
            url: '/api/validate-password/',
            data: JSON.stringify({'password': password}),
            dataType: 'json',
            contentType: 'application/json; charset=utf-8',
            success: function(data) {
                if (! data.result) {
                    return;
                }

                $policyContainer.empty();
                $policyContainer.removeClass('a2-password-ok a2-password-nok');
                for (var i = 0; i < data.checks.length; i++) {
                    var error = data.checks[i];

                    var $rule = $('<span class="a2-password-policy-rule"/>');
                    $rule.text(error.label)
                    $rule.appendTo($policyContainer);
                    $rule.toggleClass('a2-password-ok', error.result);
                    $rule.toggleClass('a2-password-nok', ! error.result);
                }
            }
        });
    }
    function validate_password(event) {
        var $input = $(event.target);
        setTimeout(function () {
            get_validation($input);
        }, 0);
    }
    return function (id) {
        var $input = $('#' + id);
        $input.on('keyup.a2-password-validate paste.a2-password-validate', validate_password);
    }
})();

a2_password_show_last_char = (function () {
    function debounce(func, milliseconds) {
        var timer;

        return function() {
            window.clearTimeout(timer);
            timer = window.setTimeout(function() {
                func();
            }, milliseconds);
        };
    }
    return function(id) {
        var $input = $('#' + id);
        var last_char_id = id + '-last-char';

        var $span = $('<span class="a2-password-show-last-char" id="' + last_char_id + '"/>');

        function show_last_char(event) {
            if (event.keyCode == 32 || event.key === undefined || event.key == ""
                || event.key == "Unidentified" || event.key.length > 1 || event.ctrlKey) {
                return;
            }
            // import input's layout to the span
            $span.css({
                'position': 'absolute',
                'font-size': $input.css('font-size'),
                'font-family': $input.css('font-family'),
                'line-height': $input.css('line-height'),
                'padding-top': $input.css('padding-top'),
                'padding-bottom': $input.css('padding-bottom'),
                'margin-top': $input.css('margin-top'),
                'margin-bottom': $input.css('margin-bottom'),
                'border-top-width': $input.css('border-top-width'),
                'border-bottom-width': $input.css('border-bottom-width'),
                'border-style': 'hidden',
                'top': $input.position().top,
                'left': $input.position().left,
            });
            var duration = 1000;
            var id = $input.attr('id');
            var last_char_id = id + '-last-char';
            $('#' + last_char_id)
                .text(event.key)
                .animate({'opacity': 1}, {
                    duration: 50,
                    queue: false,
                    complete: function () {
                        var $this = $(this);
                        window.setTimeout(
                            debounce(function () {
                                $this.animate({'opacity': 0}, {
                                    duration: 50
                                });
                            }, duration), duration);
                    }
                });
        }
        // place span absolutery in padding-left of the input
        $input.before($span);
        $input.on('keypress.a2-password-show-last-char', show_last_char);
    }
})();
