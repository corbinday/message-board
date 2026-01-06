with
    current_user_id := global current_user.id,
    friendships := (
        select Friend
        filter .user1.id = current_user_id
            or .user2.id = current_user_id
    )
select friendships {
    id,
    friend := (
        select User
        filter .id = (
            friendships.user1.id if friendships.user2.id = current_user_id
            else friendships.user2.id
        )
    ) {
        id,
        username,
        avatar
    },
    created_at
}
order by .created_at desc;

