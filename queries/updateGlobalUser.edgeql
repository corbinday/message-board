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
      avatar := <optional bytes>$avatar ?? .avatar,
      username := <optional str>$username ?? .username,
      email := <optional str>$email ?? .email
    }
  )
select updated_user {*};


