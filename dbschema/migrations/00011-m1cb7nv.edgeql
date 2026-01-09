CREATE MIGRATION m1cb7nvkvn3r6rqdjtxrx5b4s4wdoq5mtior2ebfrltb2bbs2in4da
    ONTO m1otceflqvxjslq6xb2dnssim7y3djkyxjiwl2pddqoizt5rqnf6oq
{
  CREATE ABSTRACT TYPE default::PixelGraphic {
      CREATE REQUIRED LINK creator: default::User;
      CREATE REQUIRED PROPERTY binary: std::bytes;
      CREATE REQUIRED PROPERTY created_at: std::datetime {
          SET default := (std::datetime_of_statement());
      };
      CREATE REQUIRED PROPERTY size: default::BoardType;
      CREATE REQUIRED PROPERTY updated_at: std::datetime {
          SET default := (std::datetime_of_statement());
      };
  };
  CREATE TYPE default::StaticImage EXTENDING default::PixelGraphic;
  CREATE TYPE default::Avatar EXTENDING default::StaticImage {
      CREATE CONSTRAINT std::expression ON ((.size = default::BoardType.Stellar)) {
          SET errmessage := 'Avatars must use the Stellar (16x16) board type';
      };
  };
  ALTER TYPE default::User {
      DROP PROPERTY avatar;
  };
  ALTER TYPE default::User {
      CREATE LINK avatar: default::Avatar;
  };
  ALTER TYPE default::Message {
      CREATE REQUIRED LINK graphic: default::PixelGraphic {
          SET REQUIRED USING (<default::PixelGraphic>{});
      };
      ALTER LINK sender {
          SET REQUIRED USING (<default::User>{});
      };
      DROP PROPERTY created_at;
  };
  ALTER TYPE default::Message {
      CREATE PROPERTY is_read: std::bool {
          SET default := false;
      };
  };
  ALTER TYPE default::Message {
      DROP PROPERTY payload;
  };
  ALTER TYPE default::Message {
      CREATE PROPERTY sent_at: std::datetime {
          SET default := (std::datetime_of_statement());
      };
  };
  CREATE TYPE default::PixelAnimation EXTENDING default::PixelGraphic {
      CREATE REQUIRED PROPERTY frame_delay_ms: std::int16 {
          SET default := 100;
          CREATE CONSTRAINT std::max_value(2000);
          CREATE CONSTRAINT std::min_value(10);
      };
      CREATE REQUIRED PROPERTY frames: std::int16;
  };
};
