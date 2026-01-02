select assert_single(
  select Board {*}
  filter .id = <uuid>$board_id and assert_single(
    .owner.identity = global ext::auth::ClientTokenIdentity
  )
);