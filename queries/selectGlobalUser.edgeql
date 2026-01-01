select assert_single(
    select User {*}
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
);