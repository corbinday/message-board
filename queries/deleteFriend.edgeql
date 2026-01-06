delete Friend
filter (
    (.user1.id = global current_user.id and .user2.id = <uuid>$friend_id)
    or (.user2.id = global current_user.id and .user1.id = <uuid>$friend_id)
);


