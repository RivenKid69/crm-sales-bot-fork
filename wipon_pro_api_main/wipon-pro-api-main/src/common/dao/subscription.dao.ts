import { Entity, PrimaryGeneratedColumn, Column, CreateDateColumn, UpdateDateColumn, DeleteDateColumn } from 'typeorm';

@Entity('subscriptions')
export class SubscriptionDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  user_id: number;

  @Column()
  is_active: boolean;

  @Column({ type: 'varchar', nullable: true })
  type: string | null;

  @Column()
  paid_name: string;

  @Column({
    type: 'varchar',
    length: 12,
  })
  paid_bin: string;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;

  @Column()
  expires_at: Date;

  @DeleteDateColumn()
  deleted_at: Date;
}
