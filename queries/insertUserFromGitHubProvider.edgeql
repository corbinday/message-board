with
  identity := (select global ext::auth::ClientTokenIdentity),
insert User {
  identity := identity,
  email := <str>$email
}