CREATE MIGRATION m1eh26dmn5yviqxkgmbcsrhlsi3wqqmnn7s5euxdxa5hvivuqllqfq
    ONTO m1ym52v55a5odbkq7j4lyboi2i66buyt4q2n5ighmjr7hqrb3ci4za
{
  ALTER TYPE default::Board {
      CREATE PROPERTY secret_updated_at: std::datetime {
          CREATE REWRITE
              UPDATE 
              USING ((IF EXISTS ((.secret_key_hash ?? <optional std::str>{})) THEN std::datetime_of_statement() ELSE .secret_updated_at));
      };
  };
};
