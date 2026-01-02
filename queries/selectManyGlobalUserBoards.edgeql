select Board {*}
filter assert_single(
    .owner.identity = global ext::auth::ClientTokenIdentity
);