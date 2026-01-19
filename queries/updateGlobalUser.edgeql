with
  user := assert_single(
    select User
    filter assert_single(
      .identity = global ext::auth::ClientTokenIdentity
    )
  ),
  updated_user := (
    update user
    set {
      avatar := (select Avatar filter .id = <uuid>$avatar_id) if exists(<optional uuid>$avatar_id ?? <optional uuid>{}) else .avatar,
      username := <optional str>$username ?? .username,
      email := <optional str>$email ?? .email
    }
  )
select updated_user {**};