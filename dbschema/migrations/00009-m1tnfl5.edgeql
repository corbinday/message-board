CREATE MIGRATION m1tnfl5o2j5x53rsmwdul4zy342qfdl34jvnqruu2ioqd344ni4nra
    ONTO m12ynowoyhkjkuvafbhnfxvlntmr66lqiijpio2dbpacfrbtdrn6oa
{
  CREATE TYPE default::Friend {
      CREATE REQUIRED LINK user1: default::User;
      CREATE REQUIRED LINK user2: default::User;
      CREATE CONSTRAINT std::exclusive ON ((.user1, .user2));
      CREATE CONSTRAINT std::expression ON ((.user1 != .user2)) {
          SET errmessage := 'Cannot be friends with yourself';
      };
      CREATE REQUIRED PROPERTY created_at: std::datetime {
          CREATE REWRITE
              INSERT 
              USING (std::datetime_of_statement());
      };
  };
  CREATE TYPE default::FriendRequest {
      CREATE REQUIRED LINK recipient: default::User;
      CREATE REQUIRED LINK sender: default::User;
      CREATE CONSTRAINT std::exclusive ON ((.sender, .recipient));
      CREATE CONSTRAINT std::expression ON ((.sender != .recipient)) {
          SET errmessage := 'Cannot send friend request to yourself';
      };
      CREATE REQUIRED PROPERTY created_at: std::datetime {
          CREATE REWRITE
              INSERT 
              USING (std::datetime_of_statement());
      };
  };
  ALTER TYPE default::User {
      CREATE PROPERTY avatar: std::bytes;
  };
};
