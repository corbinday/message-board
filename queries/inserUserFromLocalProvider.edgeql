with
  identity := (select global ext::auth::ClientTokenIdentity),
  emailFactor := (
    select ext::auth::EmailFactor {email} 
    filter .identity.id = identity.id
  ),
insert User {
  identity := identity,
  email := emailFactor.email
}