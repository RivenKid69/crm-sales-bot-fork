import { Entity, PrimaryGeneratedColumn, Column, CreateDateColumn, UpdateDateColumn } from 'typeorm';

@Entity('auth_codes')
export class AuthCodeDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  user_id: number;

  @Column({
    type: 'varchar',
    length: 6,
  })
  code: string;

  @Column({
    type: 'timestamp',
  })
  expires_at: Date;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;
}
