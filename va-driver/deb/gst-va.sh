# what the user manager's generator gives a session, for a login shell
tvb_va_environment=$(/usr/lib/systemd/user-environment-generators/60-tvb-va-driver)
[ -z "$tvb_va_environment" ] || export $tvb_va_environment
unset tvb_va_environment
