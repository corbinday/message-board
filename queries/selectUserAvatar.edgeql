select assert_single(
    select User
    filter .id = <uuid>$user_id
).avatar.binary;


